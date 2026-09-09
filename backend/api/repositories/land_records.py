"""Supabase/PostgREST adapter for land-record persistence."""

import os
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class PersistenceConfigurationError(RuntimeError):
    """Raised when the API has not received usable Supabase credentials."""


class RecordNotFoundError(LookupError):
    """Raised when a requested record is absent from the database."""


class PersistenceError(RuntimeError):
    """Raised for a database failure that is safe to expose as a generic API error."""


class PersistenceAuthenticationError(PersistenceError):
    """Raised when Supabase rejects the server-only credential."""


def _environment_value(name: str) -> str:
    """Read a Render secret defensively without ever logging its value."""
    value = os.getenv(name, "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


class SupabaseLandRecordRepository:
    """Keep all PostgREST details outside routes and application services."""

    table_name = "land_records"
    DB_COLUMNS = {
        "id", "created_at", "updated_at", "owner_name", "father_name",
        "district", "tehsil", "village", "khata_number", "khasra_number",
        "document_url", "area", "area_unit", "land_type", "record_date",
        "validation_status", "validation_result", "confidence", "processing_status",
    }

    def __init__(
        self, *, url: str | None = None, key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._url = (url if url is not None else _environment_value("SUPABASE_URL")).strip().rstrip("/")
        self._key = (key if key is not None else _environment_value("SUPABASE_SERVICE_ROLE_KEY")).strip()
        self._transport = transport

    @classmethod
    def _to_db_payload(cls, values: dict[str, Any]) -> dict[str, Any]:
        payload = dict(values)
        filtered = {k: v for k, v in payload.items() if k in cls.DB_COLUMNS and v is not None}
        return filtered if filtered else payload

    @classmethod
    def _from_db_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        data = dict(row)
        if "land_area" in data and "area" not in data:
            data["area"] = data["land_area"]
        if "status" in data:
            if "processing_status" not in data:
                data["processing_status"] = data["status"]
            if "validation_status" not in data:
                data["validation_status"] = data["status"]
        return data

    def _headers(self, *, return_representation: bool = False) -> dict[str, str]:
        if not self._url.startswith(("https://", "http://")) or not self._key:
            raise PersistenceConfigurationError(
                "Database persistence is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
            )
        headers = {"apikey": self._key, "Authorization": f"Bearer {self._key}"}
        if return_representation:
            headers["Prefer"] = "return=representation"
        return headers

    @property
    def _endpoint(self) -> str:
        return f"{self._url}/rest/v1/{self.table_name}"

    async def _request(
        self, method: str, *, params: Mapping[str, str] | None = None, json: dict[str, Any] | None = None,
        return_representation: bool = False,
    ) -> list[dict[str, Any]]:
        headers = self._headers(return_representation=return_representation)
        try:
            async with httpx.AsyncClient(timeout=10.0, transport=self._transport) as client:
                response = await client.request(method, self._endpoint, headers=headers, params=params, json=json)
        except httpx.HTTPError as exc:
            raise PersistenceError("Database request failed") from exc

        if response.status_code in {401, 403}:
            logger.warning("Supabase rejected backend credentials with HTTP %s", response.status_code)
            raise PersistenceAuthenticationError("Database authentication failed. Check server-side Supabase configuration.")
        if response.status_code >= 400:
            logger.warning("Supabase request failed with HTTP %s", response.status_code)
            raise PersistenceError("Database request failed")
        if not response.content:
            return []
        payload = response.json()
        if not isinstance(payload, list):
            raise PersistenceError("Database returned an unexpected response")
        return payload

    async def create(self, values: dict[str, Any]) -> dict[str, Any]:
        db_payload = self._to_db_payload(values)
        rows = await self._request("POST", json=db_payload, return_representation=True)
        if not rows:
            raise PersistenceError("Database did not return the created record")
        return self._from_db_row(rows[0])

    async def get(self, record_id: str) -> dict[str, Any]:
        rows = await self._request("GET", params={"id": f"eq.{record_id}", "select": "*"})
        if not rows:
            raise RecordNotFoundError(record_id)
        return self._from_db_row(rows[0])

    async def list(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        rows = await self._request(
            "GET", params={"select": "*", "order": "created_at.desc", "limit": str(limit), "offset": str(offset)}
        )
        return [self._from_db_row(row) for row in rows]

    async def update(self, record_id: str, values: dict[str, Any]) -> dict[str, Any]:
        db_payload = self._to_db_payload(values)
        rows = await self._request(
            "PATCH", params={"id": f"eq.{record_id}"}, json=db_payload, return_representation=True
        )
        if not rows:
            raise RecordNotFoundError(record_id)
        return self._from_db_row(rows[0])

    async def delete(self, record_id: str) -> None:
        await self.get(record_id)
        await self._request("DELETE", params={"id": f"eq.{record_id}"})
