"""Bridge the existing OCR pipeline to persisted FastAPI records."""

import copy
from datetime import datetime, timezone
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status

from api.schemas.records import LandRecordCreate, LandRecordRead
from api.services.land_record_service import LandRecordService
from app.services.document_ingestion_service import MAX_DOCUMENT_SIZE_BYTES
from app.services.ocr_pipeline_service import process_land_record_document


class RecordProcessingService:
    """Run the existing document pipeline, then persist its structured result."""

    def __init__(self, record_service: LandRecordService) -> None:
        self._record_service = record_service

    async def process(self, document: UploadFile) -> dict[str, Any]:
        if not document.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A document filename is required")

        suffix = Path(document.filename).suffix.casefold()
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="land-record-api-", suffix=suffix, delete=False) as temporary:
                temp_path = temporary.name
                total = 0
                while chunk := await document.read(64 * 1024):
                    total += len(chunk)
                    if total > MAX_DOCUMENT_SIZE_BYTES:
                        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Document exceeds 20 MiB")
                    temporary.write(chunk)

            result = process_land_record_document(temp_path)
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass

        public_result = copy.deepcopy(result)
        if isinstance(public_result.get("document"), dict):
            public_result["document"].pop("source_path", None)
            public_result["document"]["filename"] = document.filename

        if result.get("status") == "failed":
            return {"pipeline": public_result, "record": None}

        record = await self._record_service.create(self._to_land_record(result))
        return {"pipeline": public_result, "record": record}

    @staticmethod
    def _to_land_record(result: dict[str, Any]) -> LandRecordCreate:
        normalized = result.get("normalized_data") if isinstance(result.get("normalized_data"), dict) else {}
        validation = result.get("validation") if isinstance(result.get("validation"), dict) else None
        area = normalized.get("area") if isinstance(normalized.get("area"), dict) else {}
        return LandRecordCreate(
            owner_name=normalized.get("owner_name"),
            father_name=normalized.get("father_name"),
            district=normalized.get("district"),
            tehsil=normalized.get("tehsil"),
            village=normalized.get("village"),
            khata_number=normalized.get("khata_number"),
            khasra_number=normalized.get("khasra_number"),
            area=area.get("value"),
            area_unit=area.get("unit"),
            land_type=normalized.get("land_type"),
            record_date=datetime.now(timezone.utc).date().isoformat(),
            validation_status="valid" if validation and validation.get("is_valid") else "needs_review",
            validation_result=validation,
            confidence=result.get("confidence") if isinstance(result.get("confidence"), dict) else None,
            processing_status=str(result.get("status", "unknown")),
        )
