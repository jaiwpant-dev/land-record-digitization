"""Orchestrate the existing single-record land-record OCR pipeline.

This module deliberately keeps evidence from each layer separate.  It does not
try to repair OCR output or replace values produced by the extractor.
"""

import os
from pathlib import Path
import tempfile
from typing import Any

from app.services.confidence_service import calculate_field_confidence
from app.services.document_ingestion_service import ingest_document
from app.services.extraction_service import FIELD_LABELS, extract_land_record_fields
from app.services.normalization_service import normalize_land_record
from app.services.validation_service import validate_land_record


def _failure(raw_ocr_text: str, stage: str, message: str) -> dict[str, Any]:
    """Return a consistent, non-destructive failed pipeline result."""
    return {
        "status": "failed",
        "raw_ocr_text": raw_ocr_text,
        "extracted_data": None,
        "normalized_data": None,
        "validation": None,
        "ocr_word_confidences": [],
        "confidence": None,
        "errors": [{"stage": stage, "message": message}],
    }


def _contains_multiple_records(raw_ocr_text: str) -> bool:
    """Detect repeated exact labels before the single-record parser can discard data."""
    lines = [line.strip() for line in raw_ocr_text.splitlines() if line.strip()]
    return any(lines.count(f"{label}:") > 1 for label in FIELD_LABELS)


def process_raw_ocr_text(
    raw_ocr_text: str, ocr_word_confidences: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Parse, normalize, and validate raw OCR text for one land-record document.

    Input must be the unmodified string returned by the OCR layer.  The result
    always retains that string and, after successful extraction, the original
    extracted values in both ``extracted_data`` and ``normalized_data``'s
    ``original_values``.  This baseline parser supports exactly one record;
    repeated field-label groups are rejected rather than silently selecting one.
    """
    if not isinstance(raw_ocr_text, str):
        raise TypeError("Raw OCR text must be a string")
    if not raw_ocr_text.strip():
        return _failure(raw_ocr_text, "ocr", "OCR produced no text")
    if _contains_multiple_records(raw_ocr_text):
        return _failure(
            raw_ocr_text,
            "extraction",
            "Multiple land-record label groups are not supported by the single-record parser",
        )

    try:
        extracted_data = extract_land_record_fields(raw_ocr_text)
    except (TypeError, ValueError) as exc:
        return _failure(raw_ocr_text, "extraction", str(exc))

    try:
        normalized_data = normalize_land_record(extracted_data)
    except (TypeError, ValueError) as exc:
        return _failure(raw_ocr_text, "normalization", str(exc))

    try:
        validation = validate_land_record(normalized_data)
    except (TypeError, ValueError) as exc:
        return _failure(raw_ocr_text, "validation", str(exc))

    try:
        confidence = calculate_field_confidence(
            extracted_data, normalized_data, validation, ocr_word_confidences
        )
    except (TypeError, ValueError) as exc:
        return _failure(raw_ocr_text, "confidence", str(exc))

    return {
        "status": "complete" if validation["is_valid"] else "needs_review",
        "raw_ocr_text": raw_ocr_text,
        "extracted_data": extracted_data,
        "normalized_data": normalized_data,
        "validation": validation,
        "ocr_word_confidences": ocr_word_confidences or [],
        "confidence": confidence,
        "errors": [],
    }


def process_land_record_image(image_path: str, language: str = "eng") -> dict[str, Any]:
    """Run the existing Tesseract OCR service and the downstream pipeline."""
    # Keep downstream text processing usable when OCR-only dependencies are not
    # installed (for example, in a service that receives persisted OCR text).
    try:
        from app.services.ocr_service import OcrProcessingError, extract_ocr_result_from_image
    except ImportError as exc:
        return _failure("", "ocr", f"OCR dependencies are unavailable: {exc}")

    try:
        ocr_result = extract_ocr_result_from_image(image_path, language=language)
    except OcrProcessingError as exc:
        return _failure(exc.raw_text, "ocr", str(exc))
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _failure("", "ocr", str(exc))
    return process_raw_ocr_text(
        ocr_result["raw_text"], ocr_result["word_confidences"]
    )


def process_land_record_document(document_path: str, language: str = "eng") -> dict[str, Any]:
    """Run Layer 1 ingestion before sending an admitted image to OCR."""
    ingestion = ingest_document(document_path)
    if ingestion["status"] != "accepted":
        return {
            **_failure("", "ingestion", ingestion["errors"][0]["message"]),
            "document": None,
        }

    rendered_path: str | None = None
    source_path = ingestion["document"]["source_path"]
    try:
        if ingestion["document"]["format"] == "pdf":
            # The pipeline handles one record per request, so render only page
            # one rather than silently combining different records in a PDF.
            from pdf2image import convert_from_path

            pages = convert_from_path(source_path, dpi=300, first_page=1, last_page=1)
            if not pages:
                raise ValueError("PDF has no renderable first page")
            descriptor, rendered_path = tempfile.mkstemp(prefix="land-record-pdf-", suffix=".png")
            os.close(descriptor)
            pages[0].save(rendered_path, format="PNG")
            source_path = rendered_path

        from app.services.preprocessing_service import preprocess_image

        preprocessing = preprocess_image(source_path)
    except Exception as exc:
        # pdf2image raises library-specific errors for malformed PDFs and for a
        # missing Poppler binary.  Report those as genuine preprocessing
        # failures, never as a successful OCR result or an adapter 500.
        if rendered_path:
            Path(rendered_path).unlink(missing_ok=True)
        return {
            **_failure("", "preprocessing", str(exc)),
            "document": ingestion["document"],
            "preprocessing": None,
        }

    try:
        result = process_land_record_image(preprocessing["processed_path"], language=language)
    finally:
        Path(preprocessing["processed_path"]).unlink(missing_ok=True)
        if rendered_path:
            Path(rendered_path).unlink(missing_ok=True)
    result["document"] = ingestion["document"]
    result["preprocessing"] = {
        key: value for key, value in preprocessing.items() if key != "processed_path"
    }
    return result
