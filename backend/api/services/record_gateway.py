"""Placeholder integration port; contains neither OCR nor database implementation."""

from fastapi import UploadFile


class IntegrationNotConfiguredError(RuntimeError):
    """Raised until concrete OCR and record-store adapters are explicitly wired."""


class RecordGateway:
    """The sole API-facing port for future document processing and retrieval."""

    async def submit(self, document: UploadFile) -> dict[str, object]:
        raise IntegrationNotConfiguredError(
            "Document processing is not connected yet; OCR and persistence adapters have not been configured."
        )

    async def get_record(self, record_id: str) -> dict[str, object]:
        raise IntegrationNotConfiguredError(
            "Record retrieval is not connected yet; no database adapter is configured."
        )

    async def list_records(self) -> dict[str, object]:
        raise IntegrationNotConfiguredError(
            "Record listing is not connected yet; no database adapter is configured."
        )
