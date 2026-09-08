"""Run the OCR service against a real sample image."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.ocr_service import extract_text_from_image


SAMPLE_DOCUMENTS = PROJECT_ROOT / "sample_documents"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def find_sample_image() -> Path | None:
    """Return the first JPG or PNG in the sample documents directory."""
    images = sorted(
        path
        for path in SAMPLE_DOCUMENTS.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    return images[0] if images else None


def main() -> int:
    image_path = Path(sys.argv[1]) if len(sys.argv) > 1 else find_sample_image()
    if image_path is None:
        print("No JPG or PNG sample image found in sample_documents/. Provide one to run the OCR test.")
        return 1

    try:
        extracted_text = extract_text_from_image(str(image_path))
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"OCR test failed: {exc}")
        return 1

    print(f"Image: {image_path}")
    print("Extracted text:")
    print(extracted_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())