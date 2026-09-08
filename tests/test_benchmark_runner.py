"""Tests for the HTTP-only ground-truth benchmark runner."""

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.serving import make_server

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.api import create_app
from benchmarks.run_benchmark import _evaluation_normalize, levenshtein_distance, run, word_error_distance


SAMPLE_IMAGE = PROJECT_ROOT / "sample_documents" / "sample_land_record.png"
GROUND_TRUTH = {
    "owner_name": "Rahul Kumar",
    "khata_number": "KH-1001",
    "area": {"value": "2.50", "unit": "hectare"},
}


def completed_result() -> dict:
    return {
        "status": "complete",
        "raw_ocr_text": "",
        "extracted_data": {"Khata No": "KH-1001"},
        "normalized_data": dict(GROUND_TRUTH),
        "validation": {
            "is_valid": True,
            "field_results": {field: {"errors": []} for field in GROUND_TRUTH},
        },
        "ocr_word_confidences": [],
        "confidence": None,
        "errors": [],
        "document": {"source_path": "private", "filename": "upload.png"},
        "preprocessing": {},
    }


def generic_ocr_result() -> dict:
    return {
        "status": "failed",
        "raw_ocr_text": "नमस्ते\n",
        "extracted_data": None,
        "normalized_data": None,
        "validation": None,
        "ocr_word_confidences": [],
        "confidence": None,
        "errors": [{"stage": "extraction", "message": "expected for a word crop"}],
        "document": {"source_path": "private", "filename": "upload.png"},
        "preprocessing": {},
    }


class BenchmarkRunnerTests(unittest.TestCase):
    def test_levenshtein_distance(self) -> None:
        self.assertEqual(levenshtein_distance("khasra", "kharsa"), 2)
        self.assertEqual(levenshtein_distance("", "abc"), 3)

    def test_runner_posts_manifest_image_to_http_endpoint_and_aggregates_metrics(self) -> None:
        with patch("app.api.process_land_record_document", return_value=completed_result()):
            server = make_server("127.0.0.1", 0, create_app({"TESTING": True}))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with tempfile.TemporaryDirectory() as directory:
                    manifest_path = Path(directory) / "manifest.json"
                    manifest_path.write_text(json.dumps({
                        "dataset": {"name": "test", "license": "CC BY 4.0", "source_url": "https://example.test"},
                        "samples": [{"id": "one", "image": str(SAMPLE_IMAGE), "ground_truth": GROUND_TRUTH}],
                    }), encoding="utf-8")
                    report = run(manifest_path, f"http://127.0.0.1:{server.server_port}/api/v1/land-records/ocr", 10)
            finally:
                server.shutdown()
                thread.join()

        self.assertEqual(report["evaluated_images"], 1)
        self.assertEqual(report["extraction_success_rate"], 1.0)
        self.assertEqual(report["field_metrics"]["khata_number"]["raw_exact_match_rate"], 1.0)
        self.assertEqual(report["field_metrics"]["khata_number"]["normalized_match_rate"], 1.0)
        self.assertEqual(report["field_metrics"]["owner_name"]["character_error_rate"], 0.0)
        self.assertEqual(report["field_metrics"]["owner_name"]["word_error_rate"], 0.0)
        self.assertEqual(report["macro_average_raw_exact_match_rate"], 1.0)
        self.assertEqual(report["record_normalized_match_rate"], 1.0)
        self.assertEqual(report["pipeline_status_counts"], {"complete": 1})

    def test_field_extraction_reports_documented_normalized_match_without_repairing_values(self) -> None:
        result = completed_result()
        result["normalized_data"]["owner_name"] = "  rahul   kumar  "
        with patch("app.api.process_land_record_document", return_value=result):
            server = make_server("127.0.0.1", 0, create_app({"TESTING": True}))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with tempfile.TemporaryDirectory() as directory:
                    manifest_path = Path(directory) / "manifest.json"
                    manifest_path.write_text(json.dumps({
                        "dataset": {"name": "test"},
                        "samples": [{"id": "one", "image": str(SAMPLE_IMAGE), "ground_truth": GROUND_TRUTH}],
                    }), encoding="utf-8")
                    report = run(manifest_path, f"http://127.0.0.1:{server.server_port}/api/v1/land-records/ocr", 10)
            finally:
                server.shutdown()
                thread.join()

        owner = report["field_metrics"]["owner_name"]
        self.assertEqual(owner["raw_exact_match_rate"], 0.0)
        self.assertEqual(owner["normalized_match_rate"], 1.0)
        self.assertEqual(owner["word_error_rate"], 0.0)
        self.assertEqual(report["record_raw_exact_match_rate"], 0.0)
        self.assertEqual(report["record_normalized_match_rate"], 1.0)

    def test_evaluation_normalization_and_word_error_are_comparison_only(self) -> None:
        self.assertEqual(_evaluation_normalize("  RAHUL\tKumar "), "rahul kumar")
        self.assertEqual(_evaluation_normalize("123/2"), "123/2")
        self.assertEqual(word_error_distance("rahul kumar", "rahul kumar"), 0)
        self.assertEqual(word_error_distance("khata 1001", "khata 1002"), 1)

    def test_runner_skips_missing_and_unsupported_manifest_images(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            manifest_path.write_text(json.dumps({
                "dataset": {"name": "test"},
                "samples": [
                    {"id": "missing", "image": "missing.png", "ground_truth": {}},
                    {"id": "text", "image": "image.txt", "ground_truth": {}},
                ],
            }), encoding="utf-8")
            report = run(manifest_path, "http://127.0.0.1:1", 1)

        self.assertEqual(report["evaluated_images"], 0)
        self.assertIsNone(report["extraction_success_rate"])
        self.assertEqual(report["skipped_images"], [
            {"id": "missing", "reason": "image_not_found"},
            {"id": "text", "reason": "unsupported_image_extension"},
        ])

    def test_generic_ocr_mode_scores_raw_ocr_without_claiming_field_accuracy(self) -> None:
        with patch("app.api.process_land_record_document", return_value=generic_ocr_result()):
            server = make_server("127.0.0.1", 0, create_app({"TESTING": True}))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with tempfile.TemporaryDirectory() as directory:
                    manifest_path = Path(directory) / "manifest.json"
                    manifest_path.write_text(json.dumps({
                        "benchmark_type": "generic_ocr",
                        "dataset": {"name": "test"},
                        "samples": [{"id": "hindi-word", "image": str(SAMPLE_IMAGE), "ground_truth": "नमस्ते"}],
                    }), encoding="utf-8")
                    report = run(manifest_path, f"http://127.0.0.1:{server.server_port}/api/v1/land-records/ocr", 10)
            finally:
                server.shutdown()
                thread.join()

        self.assertEqual(report["exact_match_rate"], 1.0)
        self.assertEqual(report["character_error_rate"], 0.0)
        # The word crop supplies OCR evidence, but the unmodified land-record
        # endpoint correctly rejects it as an incomplete record (HTTP 422).
        self.assertEqual(report["successful_http_requests"], 0)
        self.assertEqual(report["failed_http_requests"], 1)
        self.assertEqual(report["http_responses_received"], 1)
        self.assertEqual(report["ocr_text_available"], 1)
        self.assertIsNone(report["land_record_field_extraction_accuracy"])


if __name__ == "__main__":
    unittest.main()
