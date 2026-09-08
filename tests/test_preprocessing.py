"""Focused Layer 2 tests; generated images isolate image operations from OCR."""

import random
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from PIL import Image, ImageDraw
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

from app.services.preprocessing_service import preprocess_image


SAMPLE_IMAGE = PROJECT_ROOT / "sample_documents" / "sample_land_record.png"


@unittest.skipUnless(PILLOW_AVAILABLE, "Pillow is required for image preprocessing tests")
class PreprocessingTests(unittest.TestCase):
    def _operation_names(self, result):
        return {operation["name"] for operation in result["operations"]}

    def _close_processed(self, result):
        Path(result["processed_path"]).unlink(missing_ok=True)

    def test_real_sample_creates_a_separate_grayscale_derivative(self) -> None:
        original_bytes = SAMPLE_IMAGE.read_bytes()
        result = preprocess_image(SAMPLE_IMAGE)
        try:
            self.assertNotEqual(Path(result["processed_path"]), SAMPLE_IMAGE)
            self.assertIn("grayscale", self._operation_names(result))
            self.assertEqual(SAMPLE_IMAGE.read_bytes(), original_bytes)
            with Image.open(result["processed_path"]) as processed:
                self.assertEqual(processed.mode, "L")
        finally:
            self._close_processed(result)

    def test_noisy_image_receives_a_readable_derivative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "noisy.png"
            image = Image.new("L", (800, 500), 255)
            pixels = image.load()
            random.seed(1)
            for _ in range(12_000):
                pixels[random.randrange(800), random.randrange(500)] = random.choice((0, 255))
            image.save(source)
            result = preprocess_image(source)
            try:
                self.assertTrue(Path(result["processed_path"]).is_file())
                self.assertIn("grayscale", self._operation_names(result))
            finally:
                self._close_processed(result)

    def test_low_resolution_image_is_upscaled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "small.png"
            Image.new("L", (400, 200), 255).save(source)
            result = preprocess_image(source)
            try:
                self.assertIn("upscale", self._operation_names(result))
                self.assertGreaterEqual(result["processed_quality"]["width"], 800)
            finally:
                self._close_processed(result)

    def test_low_contrast_image_receives_contrast_enhancement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "low-contrast.png"
            image = Image.new("L", (1400, 500), 185)
            ImageDraw.Draw(image).text((100, 100), "Land Record", fill=165)
            image.save(source)
            result = preprocess_image(source)
            try:
                self.assertIn("autocontrast", self._operation_names(result))
            finally:
                self._close_processed(result)

    def test_skewed_image_is_processed_without_touching_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "skewed.png"
            image = Image.new("L", (1000, 500), 255)
            drawing = ImageDraw.Draw(image)
            for y in range(80, 420, 50):
                drawing.line((100, y, 900, y), fill=0, width=4)
            image.rotate(3, fillcolor=255).save(source)
            original_bytes = source.read_bytes()
            result = preprocess_image(source)
            try:
                self.assertTrue(Path(result["processed_path"]).is_file())
                self.assertEqual(source.read_bytes(), original_bytes)
            finally:
                self._close_processed(result)

    def test_invalid_image_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "invalid.png"
            source.write_bytes(b"not an image")
            with self.assertRaises(ValueError):
                preprocess_image(source)


if __name__ == "__main__":
    unittest.main()
