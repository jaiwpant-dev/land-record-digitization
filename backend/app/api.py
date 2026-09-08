"""HTTP adapter for the existing land-record document pipeline.

This module owns request parsing and temporary upload lifecycle only.  OCR and
all downstream decisions remain in ``process_land_record_document``.
"""

import copy
import os
import tempfile
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from app.services.document_ingestion_service import MAX_DOCUMENT_SIZE_BYTES, SUPPORTED_FORMATS
from app.services.ocr_pipeline_service import process_land_record_document
from app.services.ocr_service import SUPPORTED_OCR_LANGUAGES


UPLOAD_FIELD_NAME = "document"
UPLOAD_CHUNK_SIZE_BYTES = 64 * 1024


def _upload_limit_from_environment() -> int:
    """Read an optional stricter API upload limit without exceeding Layer 1."""
    configured = os.getenv("LAND_RECORD_MAX_UPLOAD_BYTES")
    if configured is None:
        return MAX_DOCUMENT_SIZE_BYTES
    try:
        limit = int(configured)
    except ValueError:
        return MAX_DOCUMENT_SIZE_BYTES
    return limit if 0 < limit <= MAX_DOCUMENT_SIZE_BYTES else MAX_DOCUMENT_SIZE_BYTES


def _failure(message: str, *, stage: str = "upload") -> dict[str, Any]:
    """Match the pipeline's failure shape for errors before a file exists."""
    return {
        "status": "failed",
        "raw_ocr_text": "",
        "extracted_data": None,
        "normalized_data": None,
        "validation": None,
        "ocr_word_confidences": [],
        "confidence": None,
        "errors": [{"stage": stage, "message": message}],
        "document": None,
        "preprocessing": None,
    }


def _http_status(result: dict[str, Any]) -> int:
    """Map existing, explicit pipeline states to HTTP response semantics."""
    if result.get("status") == "complete":
        return 200
    if result.get("status") == "needs_review":
        return 422

    errors = result.get("errors")
    stage = errors[0].get("stage") if isinstance(errors, list) and errors else None
    if stage in {"upload", "ingestion"}:
        return 400
    if stage == "ocr":
        return 502
    if stage in {"preprocessing", "extraction", "normalization", "validation", "confidence"}:
        return 422
    return 500


def _public_result(result: dict[str, Any], upload_filename: str) -> dict[str, Any]:
    """Retain pipeline evidence while removing the private temporary path."""
    public = copy.deepcopy(result)
    document = public.get("document")
    if isinstance(document, dict):
        document.pop("source_path", None)
        document["filename"] = upload_filename
    return public


def create_app(config: dict[str, Any] | None = None) -> Flask:
    """Create the API application without executing OCR at import time."""
    app = Flask(__name__)
    upload_limit = _upload_limit_from_environment()
    app.config.from_mapping(
        MAX_UPLOAD_BYTES=upload_limit,
        # Leave room for multipart framing while enforcing the exact file size
        # limit during streaming below.
        MAX_CONTENT_LENGTH=upload_limit + (1024 * 1024),
    )
    if config:
        app.config.update(config)

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_: RequestEntityTooLarge):
        result = _failure(
            f"Upload exceeds the maximum allowed size of {app.config['MAX_UPLOAD_BYTES']} bytes"
        )
        return jsonify(result), 413

    @app.post("/api/v1/land-records/ocr")
    def upload_land_record():
        upload = request.files.get(UPLOAD_FIELD_NAME)
        if upload is None or not upload.filename:
            return jsonify(_failure(f"Multipart field '{UPLOAD_FIELD_NAME}' is required")), 400

        suffix = Path(upload.filename).suffix.casefold()
        if suffix not in SUPPORTED_FORMATS:
            return jsonify(_failure("Unsupported document format. Supported formats: JPG, JPEG, PNG")), 400
        language = request.form.get("language", "eng").casefold()
        if language not in SUPPORTED_OCR_LANGUAGES:
            return jsonify(_failure(f"Unsupported OCR language. Supported languages: {', '.join(sorted(SUPPORTED_OCR_LANGUAGES))}")), 400

        try:
            with tempfile.TemporaryDirectory(prefix="land-record-upload-") as directory:
                path = Path(directory) / f"upload{suffix}"
                size_bytes = 0
                with path.open("xb") as destination:
                    while chunk := upload.stream.read(UPLOAD_CHUNK_SIZE_BYTES):
                        size_bytes += len(chunk)
                        if size_bytes > app.config["MAX_UPLOAD_BYTES"]:
                            return jsonify(_failure(
                                f"Upload exceeds the maximum allowed size of {app.config['MAX_UPLOAD_BYTES']} bytes"
                            )), 413
                        destination.write(chunk)

                result = (
                    process_land_record_document(str(path))
                    if language == "eng"
                    else process_land_record_document(str(path), language=language)
                )
        except OSError:
            # Do not expose server filesystem details through the public API.
            return jsonify(_failure("Upload could not be stored safely")), 500
        except Exception:
            # The pipeline normally returns structured failures.  This is only
            # a final boundary for unexpected adapter-level errors.
            return jsonify(_failure("Unexpected processing failure", stage="api")), 500

        return jsonify(_public_result(result, upload.filename)), _http_status(result)

    return app


app = create_app()
