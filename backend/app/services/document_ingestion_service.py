"""Layer 1: validate and describe a document before it enters OCR."""

from pathlib import Path
from typing import Any


MAX_DOCUMENT_SIZE_BYTES = 20 * 1024 * 1024
SUPPORTED_FORMATS = {
    ".jpg": {"format": "jpeg", "media_type": "image/jpeg", "signature": b"\xff\xd8\xff"},
    ".jpeg": {"format": "jpeg", "media_type": "image/jpeg", "signature": b"\xff\xd8\xff"},
    ".png": {
        "format": "png",
        "media_type": "image/png",
        "signature": b"\x89PNG\r\n\x1a\n",
    },
    ".pdf": {"format": "pdf", "media_type": "application/pdf", "signature": b"%PDF-"},
}


def _rejected(source_path: str, message: str) -> dict[str, Any]:
    return {
        "status": "rejected",
        "document": None,
        "errors": [{"stage": "ingestion", "message": message}],
        "source_path": source_path,
    }


def ingest_document(
    document_path: str | Path, *, max_document_size_bytes: int = MAX_DOCUMENT_SIZE_BYTES
) -> dict[str, Any]:
    """Admit a supported image and return metadata without modifying its bytes.

    The caller retains ownership of the source file.  This function neither
    uploads, copies, converts, nor preprocesses the document.
    """
    if not isinstance(document_path, (str, Path)):
        return _rejected("", "Document path must be a string or Path")
    if not isinstance(max_document_size_bytes, int) or max_document_size_bytes <= 0:
        return _rejected(str(document_path), "Maximum document size must be a positive integer")

    path = Path(document_path)
    if not path.is_file():
        return _rejected(str(path), "Document file does not exist or is not a regular file")

    suffix = path.suffix.casefold()
    format_specification = SUPPORTED_FORMATS.get(suffix)
    if format_specification is None:
        return _rejected(
            str(path),
            "Unsupported document format. Supported formats: JPG, JPEG, PNG, PDF",
        )

    try:
        size_bytes = path.stat().st_size
    except OSError as exc:
        return _rejected(str(path), f"Document cannot be inspected: {exc}")
    if size_bytes == 0:
        return _rejected(str(path), "Document file is empty")
    if size_bytes > max_document_size_bytes:
        return _rejected(
            str(path),
            f"Document exceeds the maximum allowed size of {max_document_size_bytes} bytes",
        )

    try:
        with path.open("rb") as document_file:
            header = document_file.read(8)
    except OSError as exc:
        return _rejected(str(path), f"Document cannot be read: {exc}")
    if not header.startswith(format_specification["signature"]):
        return _rejected(
            str(path),
            f"Document content does not match the {format_specification['format'].upper()} extension",
        )

    return {
        "status": "accepted",
        "document": {
            "source_path": str(path.resolve()),
            "filename": path.name,
            "format": format_specification["format"],
            "media_type": format_specification["media_type"],
            "size_bytes": size_bytes,
        },
        "errors": [],
        "source_path": str(path),
    }
