"""Run OCR and extract fields from the real sample land record."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.extraction_service import extract_land_record_fields
from app.services.ocr_service import extract_text_from_image


IMAGE_PATH = PROJECT_ROOT / "sample_documents" / "sample_land_record.png"
EXPECTED_FIELDS = {
    "Owner Name": "Rahul Kumar",
    "Father Name": "Ramesh Kumar",
    "District": "Nainital",
    "Tehsil": "Bhimtal",
    "Village": "Demo Village",
    "Khata No": "KH-1001",
    "Khasra No": "123/2",
    "Area": "2.50 hectare",
    "Land Type": "Agricultural",
}


def main() -> int:
    raw_text = extract_text_from_image(str(IMAGE_PATH))
    extracted_fields = extract_land_record_fields(raw_text)
    assert extracted_fields == EXPECTED_FIELDS, extracted_fields
    print(extracted_fields)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())