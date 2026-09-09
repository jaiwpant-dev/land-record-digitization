"""Bridge the existing OCR pipeline to persisted FastAPI records."""

import copy
from datetime import datetime, timezone
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status

from app.services.document_ingestion_service import MAX_DOCUMENT_SIZE_BYTES
from app.services.ocr_pipeline_service import process_land_record_document
from app.services.ocr_service import SUPPORTED_OCR_LANGUAGES


class RecordProcessingService:
    """Run an uploaded document through OCR without persisting it.

    Persistence is deliberately a separate user action.  This boundary ensures
    a database outage can never hide a completed OCR result or turn processing
    into an implicit save.
    """

    async def process(self, document: UploadFile, *, language: str = "eng") -> dict[str, Any]:
        if not document.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A document filename is required")
        language = language.casefold()
        if language not in SUPPORTED_OCR_LANGUAGES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported OCR language. Supported languages: {', '.join(sorted(SUPPORTED_OCR_LANGUAGES))}",
            )

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

            result = process_land_record_document(temp_path, language=language)
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

        return {"pipeline": public_result, "record": None}
