"""Tests for orchestration of the existing OCR, parsing, normalization, and validation layers."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.ocr_pipeline_service import process_raw_ocr_text


SAMPLE_LAYOUT_TEXT = """Owner Name:
Father Name:
District:
Tehsil:
Village:
Khata No:
Khasra No:
Area:
Land Type:
Rahul Kumar
Ramesh Kumar
Nainital
Bhimtal
Demo Village
KH-1001
123/2
2.50 hectare
Agricultural
Fictional demonstration data only
"""


class OcrPipelineTests(unittest.TestCase):
    def test_normal_document_runs_through_validation(self) -> None:
        result = process_raw_ocr_text(SAMPLE_LAYOUT_TEXT)

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["extracted_data"]["Owner Name"], "Rahul Kumar")
        self.assertEqual(result["normalized_data"]["original_values"]["owner_name"], "Rahul Kumar")
        self.assertTrue(result["validation"]["is_valid"])

    def test_missing_fields_is_a_structured_extraction_failure(self) -> None:
        result = process_raw_ocr_text(SAMPLE_LAYOUT_TEXT.replace("Village:\n", ""))

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["stage"], "extraction")
        self.assertIn("Village", result["errors"][0]["message"])
        self.assertIsNone(result["normalized_data"])

    def test_ocr_identifier_mistake_is_preserved_and_flagged(self) -> None:
        raw_text = SAMPLE_LAYOUT_TEXT.replace("KH-1001", "KH-I00I")
        result = process_raw_ocr_text(raw_text)

        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["extracted_data"]["Khata No"], "KH-I00I")
        self.assertEqual(result["normalized_data"]["original_values"]["khata_number"], "KH-I00I")
        self.assertFalse(result["validation"]["field_results"]["khata_number"]["valid"])

    def test_unexpected_area_format_is_not_rewritten(self) -> None:
        raw_text = SAMPLE_LAYOUT_TEXT.replace("2.50 hectare", "two and a half bigha")
        result = process_raw_ocr_text(raw_text)

        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["normalized_data"]["original_values"]["area"], "two and a half bigha")
        self.assertEqual(result["normalized_data"]["area"], {"value": None, "unit": None})
        self.assertFalse(result["validation"]["field_results"]["area"]["valid"])

    def test_empty_ocr_output_is_safe(self) -> None:
        result = process_raw_ocr_text("  \n\t")

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["stage"], "ocr")
        self.assertEqual(result["raw_ocr_text"], "  \n\t")

    def test_partially_extracted_record_is_not_fabricated(self) -> None:
        raw_text = SAMPLE_LAYOUT_TEXT.rsplit("\n", 3)[0]
        result = process_raw_ocr_text(raw_text)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["stage"], "extraction")
        self.assertIsNone(result["extracted_data"])

    def test_multiple_records_are_rejected_until_multi_record_parsing_exists(self) -> None:
        result = process_raw_ocr_text(SAMPLE_LAYOUT_TEXT + SAMPLE_LAYOUT_TEXT)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["stage"], "extraction")
        self.assertIn("Multiple", result["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
