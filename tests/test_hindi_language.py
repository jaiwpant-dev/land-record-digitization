"""Controlled Hindi integration coverage through the public API contract."""

import io
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.api import create_app
from app.services.ocr_pipeline_service import process_land_record_document


class HindiLanguageTests(unittest.TestCase):
    sample = PROJECT_ROOT / "sample_documents" / "synthetic_hindi_land_record.png"

    def test_hindi_document_completes_full_pipeline(self) -> None:
        result = process_land_record_document(str(self.sample), language="hin")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["normalized_data"]["owner_name"], "अमित शर्मा")
        self.assertEqual(result["normalized_data"]["father_name"], "रमेश शर्मा")
        self.assertEqual(result["normalized_data"]["district"], "दिल्ली")
        self.assertEqual(result["normalized_data"]["tehsil"], "विकासनगर")
        self.assertTrue(result["validation"]["is_valid"])
        self.assertIsNotNone(result["confidence"]["overall_confidence"])

    def test_api_accepts_hindi_without_changing_response_shape(self) -> None:
        response = create_app({"TESTING": True}).test_client().post(
            "/api/v1/land-records/ocr",
            data={"document": (io.BytesIO(self.sample.read_bytes()), self.sample.name), "language": "hin"},
            content_type="multipart/form-data",
        )
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["normalized_data"]["owner_name"], "अमित शर्मा")
        self.assertIn("confidence", payload)


if __name__ == "__main__":
    unittest.main()
