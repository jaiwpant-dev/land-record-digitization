"""Confidence-layer tests; synthetic word entries isolate scoring only, not OCR."""

import csv
import re
import shutil
import subprocess
import sys
import unittest
from io import StringIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.confidence_service import calculate_field_confidence
from app.services.normalization_service import normalize_land_record
from app.services.ocr_pipeline_service import process_raw_ocr_text
from app.services.validation_service import validate_land_record


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
SAMPLE_LAYOUT_TEXT = "\n".join(
    [f"{label}:" for label in RECORD]
    + list(RECORD.values())
    + ["Fictional demonstration data only"]
)


def assess(words, record=RECORD):
    normalized = normalize_land_record(record)
    return calculate_field_confidence(record, normalized, validate_land_record(normalized), words)


def full_record_words(confidence=90):
    """Synthetic TSV-like evidence for every source token in the baseline record."""
    return [
        {"text": token, "confidence": confidence, "left": index}
        for index, value in enumerate(RECORD.values())
        for token in re.findall(r"[A-Za-z0-9]+(?:[./-][A-Za-z0-9]+)*", value)
    ]


class ConfidenceTests(unittest.TestCase):
    def test_high_medium_and_low_engine_confidence_levels(self) -> None:
        for value, level in ((96, "high"), (70, "medium"), (40, "low")):
            with self.subTest(full_field_value=value):
                result = assess(
                    [{"text": "Rahul", "confidence": value}, {"text": "Kumar", "confidence": value}]
                )
                self.assertEqual(result["fields"]["owner_name"]["confidence_level"], level)

    def test_missing_engine_confidence_remains_unavailable(self) -> None:
        field = assess([{"text": "Rahul", "confidence": None}, {"text": "Kumar", "confidence": None}])["fields"]["owner_name"]

        self.assertIsNone(field["ocr_confidence"])
        self.assertIsNone(field["final_confidence"])
        self.assertEqual(field["confidence_level"], "unavailable")

    def test_unscored_matched_word_reduces_confidence_coverage(self) -> None:
        field = assess([{"text": "Rahul", "confidence": 90}, {"text": "Kumar", "confidence": None}])["fields"]["owner_name"]

        self.assertEqual(field["token_coverage"], 1.0)
        self.assertEqual(field["confidence_coverage"], 0.5)
        self.assertEqual(field["ocr_confidence"], 90.0)
        self.assertEqual(field["final_confidence"], 45.0)

    def test_partially_recognized_multi_word_field_uses_coverage(self) -> None:
        field = assess([{"text": "Rahul", "confidence": 90}])["fields"]["owner_name"]

        self.assertEqual(field["matched_word_count"], 1)
        self.assertEqual(field["expected_word_count"], 2)
        self.assertEqual(field["token_coverage"], 0.5)
        self.assertEqual(field["ocr_confidence"], 90.0)
        self.assertEqual(field["final_confidence"], 45.0)

    def test_multi_word_confidence_is_character_weighted(self) -> None:
        field = assess([{"text": "Rahul", "confidence": 100}, {"text": "Kumar", "confidence": 50}])["fields"]["owner_name"]

        self.assertEqual(field["ocr_confidence"], 75.0)
        self.assertEqual(field["final_confidence"], 75.0)

    def test_numeric_khata_and_khasra_fields_use_engine_evidence(self) -> None:
        result = assess([{"text": "KH-1001", "confidence": 88.5}, {"text": "123/2", "confidence": 92.5}])

        self.assertEqual(result["fields"]["khata_number"]["ocr_confidence"], 88.5)
        self.assertEqual(result["fields"]["khasra_number"]["ocr_confidence"], 92.5)

    def test_ocr_mistake_is_preserved_and_validation_reduces_final_score(self) -> None:
        record = {**RECORD, "Khata No": "KH-I00I"}
        field = assess([{"text": "KH-I00I", "confidence": 90}], record)["fields"]["khata_number"]

        self.assertEqual(field["source_value"], "KH-I00I")
        self.assertEqual(field["ocr_confidence"], 90.0)
        self.assertEqual(field["validation_status"], "invalid")
        self.assertEqual(field["final_confidence"], 54.0)

    def test_normalization_does_not_replace_engine_evidence(self) -> None:
        record = {**RECORD, "Khata No": " KH-1001 "}
        field = assess([{"text": "KH-1001", "confidence": 90}], record)["fields"]["khata_number"]

        self.assertTrue(field["normalization_applied"])
        self.assertEqual(field["source_value"], " KH-1001 ")
        self.assertEqual(field["normalized_value"], "KH-1001")
        self.assertEqual(field["final_confidence"], 90.0)

    def test_field_score_retains_the_matched_raw_tsv_evidence(self) -> None:
        field = assess([{"text": "Rahul", "confidence": 90, "left": 123}])["fields"]["owner_name"]

        self.assertEqual(field["matched_ocr_words"], [{"text": "Rahul", "confidence": 90, "left": 123}])

    def test_low_ocr_confidence_is_used_without_substitution(self) -> None:
        field = assess([{"text": "Rahul", "confidence": 12}, {"text": "Kumar", "confidence": 12}])["fields"]["owner_name"]

        self.assertEqual(field["ocr_confidence"], 12.0)
        self.assertEqual(field["final_confidence"], 12.0)
        self.assertEqual(field["confidence_level"], "low")

    def test_missing_field_has_no_score_and_prevents_an_overall_score(self) -> None:
        record = {key: value for key, value in RECORD.items() if key != "Owner Name"}
        result = assess(full_record_words(), record)
        field = result["fields"]["owner_name"]

        self.assertEqual(field["validation_status"], "invalid")
        self.assertIsNone(field["final_confidence"])
        self.assertIsNone(result["overall_confidence"])
        self.assertIn("owner_name", result["overall"]["unavailable_fields"])

    def test_invalid_field_caps_overall_confidence(self) -> None:
        record = {**RECORD, "Khata No": "KH-I00I"}
        words = [
            {"text": token, "confidence": 90}
            for value in record.values()
            for token in re.findall(r"[A-Za-z0-9]+(?:[./-][A-Za-z0-9]+)*", value)
        ]
        result = assess(words, record)

        self.assertEqual(result["fields"]["khata_number"]["final_confidence"], 54.0)
        self.assertEqual(result["overall_confidence"], 54.0)
        self.assertEqual(result["overall"]["invalid_field_cap"], 54.0)

    def test_multiple_field_confidence_levels_use_the_weakest_field_for_record(self) -> None:
        words = full_record_words(95)
        for word in words:
            if word["text"] == "Bhimtal":
                word["confidence"] = 65
            if word["text"] == "Agricultural":
                word["confidence"] = 35
        result = assess(words)

        self.assertEqual(result["fields"]["district"]["confidence_level"], "high")
        self.assertEqual(result["fields"]["tehsil"]["confidence_level"], "medium")
        self.assertEqual(result["fields"]["land_type"]["confidence_level"], "low")
        self.assertEqual(result["overall_confidence"], 35.0)

    def test_ambiguous_extraction_has_no_confidence_result(self) -> None:
        text = "\n".join(
            [
                "Owner Name:", "Rahul Kumar", "Unexpected second owner", "Father Name:", "Ramesh Kumar",
                "District:", "Nainital", "Tehsil:", "Bhimtal", "Village:", "Demo Village",
                "Khata No:", "KH-1001", "Khasra No:", "123/2", "Area:", "2.50 hectare",
                "Land Type:", "Agricultural",
            ]
        )
        result = process_raw_ocr_text(text, full_record_words())

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["stage"], "extraction")
        self.assertIsNone(result["confidence"])

    def test_empty_ocr_output_stays_a_pipeline_failure(self) -> None:
        result = process_raw_ocr_text("")

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["stage"], "ocr")
        self.assertIsNone(result["confidence"])

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is not installed")
    def test_real_sample_document_uses_real_tesseract_confidence(self) -> None:
        image = PROJECT_ROOT / "sample_documents" / "sample_land_record.png"
        raw_text = subprocess.run(
            ["tesseract", str(image), "stdout", "-l", "eng"],
            check=True, capture_output=True, text=True,
        ).stdout
        tsv = subprocess.run(
            ["tesseract", str(image), "stdout", "-l", "eng", "tsv"],
            check=True, capture_output=True, text=True,
        ).stdout
        words = [
            {"text": row["text"], "confidence": float(row["conf"])}
            for row in csv.DictReader(StringIO(tsv), delimiter="\t")
            if row["text"].strip() and float(row["conf"]) >= 0
        ]

        result = process_raw_ocr_text(raw_text, words)

        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["validation"]["is_valid"])
        self.assertEqual(result["extracted_data"]["Khata No"], "KH-1001")
        self.assertIsNotNone(result["confidence"]["fields"]["khata_number"]["ocr_confidence"])


if __name__ == "__main__":
    unittest.main()
