"""Unit tests for land-record normalization."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.normalization_service import normalize_land_record


class NormalizationTests(unittest.TestCase):
    def test_clean_input(self) -> None:
        result = normalize_land_record(
            {"Owner Name": "Rahul Kumar", "Area": "2.50 hectare"}
        )

        self.assertEqual(result["owner_name"], "Rahul Kumar")
        self.assertEqual(result["area"], {"value": "2.50", "unit": "hectare"})

    def test_extra_whitespace_is_removed(self) -> None:
        result = normalize_land_record({"Village": "  Demo   Village  "})

        self.assertEqual(result["village"], "Demo Village")

    def test_identifier_formatting_is_consistent(self) -> None:
        result = normalize_land_record(
            {"Khata No": " kh - 1001 ", "Khasra No": " 123 / 2 "}
        )

        self.assertEqual(result["khata_number"], "KH-1001")
        self.assertEqual(result["khasra_number"], "123/2")

    def test_area_and_unit_are_normalized_safely(self) -> None:
        result = normalize_land_record({"Area": "2,50 hectares"})

        self.assertEqual(result["area"], {"value": "2.50", "unit": "hectare"})

    def test_missing_and_null_fields_are_safe(self) -> None:
        result = normalize_land_record({"Owner Name": None})

        self.assertIsNone(result["owner_name"])
        self.assertIsNone(result["district"])
        self.assertIsNone(result["area"])

    def test_malformed_input_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            normalize_land_record([("Owner Name", "Rahul Kumar")])

        with self.assertRaises(ValueError):
            normalize_land_record({"Unexpected": "value"})

    def test_original_values_are_preserved(self) -> None:
        source = {"Owner Name": "  Rahul   Kumar  ", "Khasra No": " 123 / 2 "}
        result = normalize_land_record(source)

        self.assertEqual(
            result["original_values"]["owner_name"], "  Rahul   Kumar  "
        )
        self.assertEqual(result["original_values"]["khasra_number"], " 123 / 2 ")

    def test_known_field_key_case_and_punctuation_variants_are_supported(self) -> None:
        result = normalize_land_record(
            {"OWNER NAME": "Rahul Kumar", "Father's Name": "Ramesh Kumar", "Khata No.": "kh - 1001"}
        )

        self.assertEqual(result["owner_name"], "Rahul Kumar")
        self.assertEqual(result["father_name"], "Ramesh Kumar")
        self.assertEqual(result["khata_number"], "KH-1001")
        self.assertEqual(result["original_values"]["khata_number"], "kh - 1001")

    def test_normalization_metadata_is_deterministic(self) -> None:
        result = normalize_land_record(
            {"Owner Name": " Rahul  Kumar ", "District": "Nainital", "Khata No": "kh - 1001", "Area": "2,50 hectares"}
        )

        self.assertTrue(result["normalization_applied"]["owner_name"])
        self.assertFalse(result["normalization_applied"]["district"])
        self.assertTrue(result["normalization_applied"]["khata_number"])
        self.assertTrue(result["normalization_applied"]["area"])

    def test_all_supported_area_units_normalize_only_when_unambiguous(self) -> None:
        for source, expected in (
            ("1 ha", {"value": "1", "unit": "hectare"}),
            ("2 acres", {"value": "2", "unit": "acre"}),
            ("3 sq m", {"value": "3", "unit": "square_meter"}),
            ("3 sq.m.", {"value": "3", "unit": "square_meter"}),
        ):
            with self.subTest(source=source):
                self.assertEqual(normalize_land_record({"Area": source})["area"], expected)

    def test_ambiguous_or_invalid_area_is_not_normalized(self) -> None:
        for source in ("2,500 hectare", "two bigha", "2 hectares approximately"):
            with self.subTest(source=source):
                result = normalize_land_record({"Area": source})
                self.assertEqual(result["area"], {"value": None, "unit": None})
                self.assertFalse(result["normalization_applied"]["area"])
                self.assertEqual(result["original_values"]["area"], source)

    def test_uncertain_ocr_value_is_not_corrected(self) -> None:
        result = normalize_land_record({"Khata No": "KH-I00I", "Land Type": "agricultural?"})

        self.assertEqual(result["khata_number"], "KH-I00I")
        self.assertEqual(result["land_type"], "agricultural?")
        self.assertFalse(result["normalization_applied"]["khata_number"])
        self.assertFalse(result["normalization_applied"]["land_type"])

    def test_duplicate_aliases_are_rejected_without_selecting_a_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate source values"):
            normalize_land_record({"Owner Name": "Rahul Kumar", "owner_name": "Another Owner"})


if __name__ == "__main__":
    unittest.main()
