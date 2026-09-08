"""Supabase/PostgREST adapter for land-record persistence."""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx


class PersistenceConfigurationError(RuntimeError):
    """Raised when the API has not received usable Supabase credentials."""


class RecordNotFoundError(LookupError):
    """Raised when a requested record is absent from the database."""


class PersistenceError(RuntimeError):
    """Raised for a database failure that is safe to expose as a generic API error."""


class SupabaseLandRecordRepository:
    """Keep all PostgREST details outside routes and application services."""

    table_name = "land_records"
    EXISTING_DB_COLUMNS = {
        "id", "created_at", "updated_at", "owner_name", "father_name",
        "district", "tehsil", "village", "khata_number", "khasra_number",
        "land_area", "land_type", "record_date", "status"
    }

    def __init__(
        self, *, url: str | None = None, key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self._key = key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
        self._transport = transport

    @classmethod
    def _to_db_payload(cls, values: dict[str, Any]) -> dict[str, Any]:
        payload = dict(values)
        if "area" in payload and "land_area" not in payload:
            payload["land_area"] = payload.pop("area")
        if "processing_status" in payload and "status" not in payload:
            payload["status"] = payload.pop("processing_status")
        elif "validation_status" in payload and "status" not in payload:
            payload["status"] = payload.pop("validation_status")
        filtered = {k: v for k, v in payload.items() if k in cls.EXISTING_DB_COLUMNS and v is not None}
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
        if not self._url or not self._key:
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

        if response.status_code >= 400:
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
