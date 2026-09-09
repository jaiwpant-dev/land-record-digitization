"""Layer 1 document-ingestion tests."""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.document_ingestion_service import ingest_document
from app.services.ocr_pipeline_service import process_land_record_document


SAMPLE_IMAGE = PROJECT_ROOT / "sample_documents" / "sample_land_record.png"


class DocumentIngestionTests(unittest.TestCase):
    def test_real_png_is_accepted_without_modifying_it(self) -> None:
        original_size = SAMPLE_IMAGE.stat().st_size
        result = ingest_document(SAMPLE_IMAGE)

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["document"]["filename"], "sample_land_record.png")
        self.assertEqual(result["document"]["format"], "png")
        self.assertEqual(result["document"]["media_type"], "image/png")
        self.assertEqual(result["document"]["size_bytes"], original_size)
        self.assertEqual(SAMPLE_IMAGE.stat().st_size, original_size)

    def test_missing_file_is_rejected(self) -> None:
        result = ingest_document(PROJECT_ROOT / "sample_documents" / "does-not-exist.png")

        self.assertEqual(result["status"], "rejected")
        self.assertIn("does not exist", result["errors"][0]["message"])

    def test_pdf_signature_is_accepted_for_rendering(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as document_file:
            document_file.write(b"%PDF-1.7")
            document_path = Path(document_file.name)
        try:
            result = ingest_document(document_path)
        finally:
            document_path.unlink(missing_ok=True)

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["document"]["format"], "pdf")

    def test_empty_document_is_rejected(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png") as document_file:
            result = ingest_document(document_file.name)

        self.assertEqual(result["status"], "rejected")
        self.assertIn("empty", result["errors"][0]["message"])

    def test_extension_and_content_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            document_path = Path(temporary_directory) / "mismatch.png"
            document_path.write_bytes(b"\xff\xd8\xff\xe0jpeg-content")
            result = ingest_document(document_path)

        self.assertEqual(result["status"], "rejected")
        self.assertIn("does not match", result["errors"][0]["message"])

    def test_size_limit_is_enforced(self) -> None:
        result = ingest_document(SAMPLE_IMAGE, max_document_size_bytes=1)

        self.assertEqual(result["status"], "rejected")
        self.assertIn("maximum allowed size", result["errors"][0]["message"])

    def test_document_pipeline_attaches_ingestion_metadata(self) -> None:
        result = process_land_record_document(str(SAMPLE_IMAGE))

        self.assertEqual(result["document"]["format"], "png")
        self.assertIn(result["status"], {"complete", "needs_review", "failed"})

    def test_rejected_document_does_not_enter_ocr_pipeline(self) -> None:
        result = process_land_record_document("missing-file.jpg")

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["stage"], "ingestion")
        self.assertIsNone(result["document"])


if __name__ == "__main__":
    unittest.main()
