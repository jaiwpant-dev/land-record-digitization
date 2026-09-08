"""Layer 3 integration and failure-handling checks using real Tesseract output."""

import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.ocr_pipeline_service import process_land_record_document, process_land_record_image
from app.services.ocr_service import extract_ocr_result_from_image


SAMPLE = PROJECT_ROOT / "sample_documents" / "sample_land_record.png"


@unittest.skipUnless(shutil.which("tesseract"), "Tesseract is not installed")
class OcrHardeningTests(unittest.TestCase):
    def test_real_sample_and_good_quality_image_complete_full_pipeline(self) -> None:
        result = process_land_record_document(str(SAMPLE))

        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["validation"]["is_valid"])
        self.assertEqual(result["extracted_data"]["Khata No"], "KH-1001")
        self.assertTrue(result["ocr_word_confidences"])
        self.assertIsNotNone(result["confidence"]["fields"]["khata_number"]["ocr_confidence"])
        self.assertIn("left", result["ocr_word_confidences"][0])
        self.assertIn("line_num", result["ocr_word_confidences"][0])

    def test_noisy_image_returns_actual_ocr_evidence_or_a_structured_failure(self) -> None:
        with Image.open(SAMPLE) as source, tempfile.TemporaryDirectory() as directory:
            image = source.convert("RGB")
            pixels = ImageDraw.Draw(image)
            randomizer = random.Random(7)
            for _ in range(5000):
                x = randomizer.randrange(image.width)
                y = randomizer.randrange(image.height)
                pixels.point((x, y), fill=(0, 0, 0) if randomizer.randrange(2) else (255, 255, 255))
            noisy_path = Path(directory) / "noisy.png"
            image.save(noisy_path)

            result = process_land_record_document(str(noisy_path))

        self.assertIn(result["status"], {"complete", "needs_review", "failed"})
        self.assertIsInstance(result["raw_ocr_text"], str)
        self.assertIn("preprocessing", result)
        if result["status"] != "failed":
            self.assertIsInstance(result["ocr_word_confidences"], list)

    def test_empty_image_is_an_ocr_failure_without_replacing_raw_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty_path = Path(directory) / "empty.png"
            Image.new("RGB", (1600, 1100), "white").save(empty_path)
            result = process_land_record_document(str(empty_path))

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["stage"], "ocr")
        self.assertEqual(result["raw_ocr_text"], "")

    def test_tsv_failure_preserves_text_from_the_completed_text_pass(self) -> None:
        expected_raw_text = extract_ocr_result_from_image(str(SAMPLE))["raw_text"]
        with patch("app.services.ocr_service.pytesseract.image_to_data", side_effect=RuntimeError("forced TSV failure")):
            result = process_land_record_image(str(SAMPLE))

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["stage"], "ocr")
        self.assertEqual(result["raw_ocr_text"], expected_raw_text)
        self.assertIn("TSV confidence extraction failed", result["errors"][0]["message"])

    def test_engine_failure_is_returned_as_a_structured_ocr_failure(self) -> None:
        with patch("app.services.ocr_service.pytesseract.image_to_string", side_effect=RuntimeError("forced OCR failure")):
            result = process_land_record_image(str(SAMPLE))

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["stage"], "ocr")
        self.assertEqual(result["raw_ocr_text"], "")
        self.assertIn("timed out or failed", result["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
