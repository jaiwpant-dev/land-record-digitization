"""HTTP integration tests for the upload adapter around the existing pipeline."""

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.api import create_app


SAMPLE_IMAGE = PROJECT_ROOT / "sample_documents" / "sample_land_record.png"
ENDPOINT = "/api/v1/land-records/ocr"


def pipeline_failure(stage: str, message: str = "forced failure") -> dict:
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
    }


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    def post(self, payload: bytes, filename: str):
        return self.client.post(
            ENDPOINT,
            data={"document": (io.BytesIO(payload), filename)},
            content_type="multipart/form-data",
        )

    def test_application_starts_and_real_sample_completes_full_pipeline(self) -> None:
        response = self.post(SAMPLE_IMAGE.read_bytes(), "land-record.png")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "complete")
        self.assertEqual(payload["document"]["filename"], "land-record.png")
        self.assertNotIn("source_path", payload["document"])
        self.assertEqual(payload["extracted_data"]["Khata No"], "KH-1001")
        self.assertTrue(payload["validation"]["is_valid"])
        self.assertIsNotNone(payload["confidence"]["fields"]["khata_number"]["ocr_confidence"])
        self.assertIsNotNone(payload["confidence"]["overall_confidence"])
        self.assertTrue(payload["ocr_word_confidences"])

    def test_missing_or_empty_upload_returns_a_structured_client_error(self) -> None:
        missing = self.client.post(ENDPOINT, data={}, content_type="multipart/form-data")
        empty = self.post(b"", "empty.png")

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.get_json()["errors"][0]["stage"], "upload")
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(empty.get_json()["errors"][0]["stage"], "ingestion")

    def test_unsupported_file_type_is_rejected_before_pipeline_processing(self) -> None:
        response = self.post(b"%PDF-1.7", "record.pdf")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["errors"][0]["stage"], "upload")

    def test_extension_signature_mismatch_is_rejected_by_existing_ingestion(self) -> None:
        response = self.post(b"\xff\xd8\xff\xe0jpeg-content", "record.png")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["errors"][0]["stage"], "ingestion")

    def test_oversized_upload_is_rejected_without_calling_pipeline(self) -> None:
        app = create_app({"TESTING": True, "MAX_UPLOAD_BYTES": 4, "MAX_CONTENT_LENGTH": 1024 * 1024})
        with patch("app.api.process_land_record_document") as pipeline:
            response = app.test_client().post(
                ENDPOINT,
                data={"document": (io.BytesIO(b"12345"), "record.png")},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json()["errors"][0]["stage"], "upload")
        pipeline.assert_not_called()

    def test_corrupt_image_reaches_existing_pipeline_and_returns_failure(self) -> None:
        response = self.post(b"\x89PNG\r\n\x1a\nnot-a-real-png", "corrupt.png")
        payload = response.get_json()

        self.assertEqual(response.status_code, 422)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["errors"][0]["stage"], "preprocessing")

    def test_ocr_failure_is_returned_as_a_gateway_error(self) -> None:
        processed_paths = []

        def ocr_failure(path: str):
            processed_paths.append(Path(path))
            self.assertTrue(Path(path).is_file())
            return pipeline_failure("ocr")

        with patch("app.api.process_land_record_document", side_effect=ocr_failure):
            response = self.post(SAMPLE_IMAGE.read_bytes(), "land-record.png")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()["errors"][0]["stage"], "ocr")
        self.assertEqual(len(processed_paths), 1)
        self.assertFalse(processed_paths[0].exists())
        self.assertFalse(processed_paths[0].parent.exists())

    def test_needs_review_validation_result_returns_422_unchanged(self) -> None:
        result = {
            **pipeline_failure("validation", "khata_number has an invalid format"),
            "status": "needs_review",
            "validation": {"is_valid": False, "field_results": {"khata_number": {"status": "invalid"}}},
            "confidence": {"overall_confidence": 54.0, "fields": {"khata_number": {"final_confidence": 54.0}}},
            "errors": [],
        }
        with patch("app.api.process_land_record_document", return_value=result):
            response = self.post(SAMPLE_IMAGE.read_bytes(), "land-record.png")

        self.assertEqual(response.status_code, 422)
        payload = response.get_json()
        self.assertEqual(payload["status"], "needs_review")
        self.assertFalse(payload["validation"]["is_valid"])
        self.assertEqual(payload["confidence"]["overall_confidence"], 54.0)


if __name__ == "__main__":
    unittest.main()
