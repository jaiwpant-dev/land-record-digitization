"""End-to-end Bengali OCR support, preserving the existing English schema."""

import io
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.ocr_pipeline_service import process_land_record_document
from app.api import create_app


class BengaliLanguageTests(unittest.TestCase):
    def test_bengali_values_complete_the_existing_pipeline(self) -> None:
        sample = PROJECT_ROOT / "sample_documents" / "synthetic_bengali_land_record.png"
        result = process_land_record_document(str(sample), language="ben")

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["normalized_data"]["owner_name"], "অনির্বাণ দত্ত")
        self.assertEqual(result["normalized_data"]["tehsil"], "কৃষ্ণনগর")
        self.assertTrue(result["validation"]["is_valid"])

    def test_unknown_language_is_rejected_without_fallback(self) -> None:
        sample = PROJECT_ROOT / "sample_documents" / "synthetic_bengali_land_record.png"
        result = process_land_record_document(str(sample), language="tam")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["stage"], "ocr")

    def test_api_accepts_optional_bengali_language_without_schema_change(self) -> None:
        sample = PROJECT_ROOT / "sample_documents" / "synthetic_bengali_land_record.png"
        response = create_app({"TESTING": True}).test_client().post(
            "/api/v1/land-records/ocr",
            data={"document": (io.BytesIO(sample.read_bytes()), sample.name), "language": "ben"},
            content_type="multipart/form-data",
        )
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["normalized_data"]["owner_name"], "অনির্বাণ দত্ত")
        self.assertIn("confidence", payload)


if __name__ == "__main__":
    unittest.main()
