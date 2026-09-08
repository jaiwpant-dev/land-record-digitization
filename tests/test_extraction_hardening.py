"""Focused Layer 4 parsing tests; OCR values are never repaired here."""

import shutil
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.extraction_service import extract_land_record_fields
from app.services.ocr_pipeline_service import process_raw_ocr_text
from app.services.ocr_service import extract_text_from_image


SAMPLE = PROJECT_ROOT / "sample_documents" / "sample_land_record.png"
RECORD = {
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


class ExtractionHardeningTests(unittest.TestCase):
    def test_spacing_and_label_format_variations_preserve_source_values(self) -> None:
        raw_text = """OWNER   NAME : Rahul  Kumar
Father's Name - Ramesh Kumar
District: Nainital
Tehsil : Bhimtal
Village: Demo Village
Khata Number: KH - 1001
Khasra No.: 123 / 2
Area : 2.50   hectare
Land Type: Agricultural
"""

        extracted = extract_land_record_fields(raw_text)

        self.assertEqual(extracted["Owner Name"], "Rahul  Kumar")
        self.assertEqual(extracted["Khata No"], "KH - 1001")
        self.assertEqual(extracted["Khasra No"], "123 / 2")
        self.assertEqual(extracted["Area"], "2.50   hectare")
        result = process_raw_ocr_text(raw_text)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["normalized_data"]["original_values"]["khata_number"], "KH - 1001")

    def test_missing_label_is_a_safe_extraction_failure(self) -> None:
        raw_text = "\n".join(f"{label}: {value}" for label, value in RECORD.items() if label != "Village")

        with self.assertRaisesRegex(ValueError, "Village"):
            extract_land_record_fields(raw_text)

    def test_invalid_identifiers_and_area_are_extracted_but_not_repaired(self) -> None:
        record = {**RECORD, "Khata No": "KH-I00I", "Khasra No": "12A/2", "Area": "zero bigha"}
        raw_text = "\n".join(f"{label}: {value}" for label, value in record.items())

        result = process_raw_ocr_text(raw_text)

        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["extracted_data"]["Khata No"], "KH-I00I")
        self.assertEqual(result["extracted_data"]["Khasra No"], "12A/2")
        self.assertEqual(result["extracted_data"]["Area"], "zero bigha")
        self.assertFalse(result["validation"]["field_results"]["khata_number"]["valid"])
        self.assertFalse(result["validation"]["field_results"]["area"]["valid"])

    def test_partial_record_does_not_produce_partial_data(self) -> None:
        raw_text = "\n".join(f"{label}:" for label in RECORD)

        with self.assertRaisesRegex(ValueError, "enough field values"):
            extract_land_record_fields(raw_text)

    def test_multiple_candidate_values_are_rejected_as_ambiguous(self) -> None:
        lines: list[str] = []
        for label, value in RECORD.items():
            lines.append(f"{label}:")
            lines.append(value)
        lines[1:2] = ["Rahul", "Rahul Kumar"]

        with self.assertRaisesRegex(ValueError, "Ambiguous OCR values for field label: Owner Name"):
            extract_land_record_fields("\n".join(lines))

    def test_duplicate_labels_are_rejected(self) -> None:
        raw_text = "\n".join(f"{label}: {value}" for label, value in RECORD.items()) + "\nOwner Name: Another Person"

        with self.assertRaisesRegex(ValueError, "Duplicate OCR field labels"):
            extract_land_record_fields(raw_text)


@unittest.skipUnless(shutil.which("tesseract"), "Tesseract is not installed")
class RealOcrExtractionTests(unittest.TestCase):
    def test_real_sample_raw_ocr_text_extracts_all_supported_fields(self) -> None:
        extracted = extract_land_record_fields(extract_text_from_image(str(SAMPLE)))

        self.assertEqual(extracted, RECORD)


if __name__ == "__main__":
    unittest.main()
