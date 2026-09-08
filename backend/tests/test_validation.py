"""Unit tests for normalized land-record validation."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.validation_service import validate_land_record


VALID_RECORD = {
    "owner_name": "Rahul Kumar",
    "father_name": "Ramesh Kumar",
    "district": "Nainital",
    "tehsil": "Bhimtal",
    "village": "Demo Village",
    "khata_number": "KH-1001",
    "khasra_number": "123/2",
    "area": {"value": "2.50", "unit": "hectare"},
    "land_type": "Agricultural",
    "original_values": {"owner_name": "Rahul Kumar"},
}


class ValidationTests(unittest.TestCase):
    def test_completely_valid_record(self) -> None:
        result = validate_land_record(VALID_RECORD)

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["field_results"]["khata_number"]["status"], "valid")
        self.assertEqual(result["field_results"]["khata_number"]["reasons"], [])

    def test_missing_required_field(self) -> None:
        record = {**VALID_RECORD, "district": None}

        result = validate_land_record(record)

        self.assertFalse(result["is_valid"])
        self.assertIn("district", result["errors"][0])

    def test_missing_owner_name(self) -> None:
        result = validate_land_record({**VALID_RECORD, "owner_name": None})

        self.assertFalse(result["is_valid"])
        self.assertIn("owner_name", result["errors"][0])

    def test_missing_khasra_number(self) -> None:
        result = validate_land_record({**VALID_RECORD, "khasra_number": None})

        self.assertFalse(result["is_valid"])
        self.assertIn("khasra_number", result["errors"][0])

    def test_missing_khata_number(self) -> None:
        result = validate_land_record({**VALID_RECORD, "khata_number": None})

        self.assertFalse(result["is_valid"])
        self.assertIn("khata_number", result["errors"][0])

    def test_missing_area(self) -> None:
        result = validate_land_record({**VALID_RECORD, "area": None})

        self.assertFalse(result["is_valid"])
        self.assertIn("area", result["errors"][0])

    def test_empty_field(self) -> None:
        result = validate_land_record({**VALID_RECORD, "owner_name": "   "})

        self.assertFalse(result["is_valid"])
        self.assertFalse(result["field_results"]["owner_name"]["valid"])

    def test_invalid_area(self) -> None:
        result = validate_land_record({**VALID_RECORD, "area": {"value": "abc", "unit": "hectare"}})

        self.assertFalse(result["is_valid"])
        self.assertTrue(any("numeric" in error for error in result["errors"]))

    def test_negative_area(self) -> None:
        result = validate_land_record({**VALID_RECORD, "area": {"value": "-1", "unit": "hectare"}})

        self.assertFalse(result["is_valid"])
        self.assertTrue(any("positive" in error for error in result["errors"]))

    def test_zero_area(self) -> None:
        result = validate_land_record({**VALID_RECORD, "area": {"value": "0", "unit": "hectare"}})

        self.assertFalse(result["is_valid"])
        self.assertTrue(any("positive" in error for error in result["errors"]))

    def test_unsupported_unit(self) -> None:
        result = validate_land_record({**VALID_RECORD, "area": {"value": "2", "unit": "bigha"}})

        self.assertFalse(result["is_valid"])
        self.assertTrue(any("unsupported unit" in error for error in result["errors"]))

    def test_invalid_khasra_number(self) -> None:
        result = validate_land_record({**VALID_RECORD, "khasra_number": "K-12/A"})

        self.assertFalse(result["is_valid"])
        self.assertFalse(result["field_results"]["khasra_number"]["valid"])

    def test_invalid_khata_number(self) -> None:
        result = validate_land_record({**VALID_RECORD, "khata_number": "1001"})

        self.assertFalse(result["is_valid"])
        self.assertFalse(result["field_results"]["khata_number"]["valid"])

    def test_zero_identifier_components_are_invalid_with_a_clear_reason(self) -> None:
        result = validate_land_record(
            {**VALID_RECORD, "khata_number": "KH-0", "khasra_number": "123/0"}
        )

        self.assertFalse(result["is_valid"])
        for field in ("khata_number", "khasra_number"):
            field_result = result["field_results"][field]
            self.assertEqual(field_result["status"], "invalid")
            self.assertIn("positive identifier components", field_result["reasons"][0])

    def test_unreadable_text_is_invalid_without_replacement(self) -> None:
        source_value = "Rahul \ufffd Kumar"
        record = {**VALID_RECORD, "owner_name": source_value}

        result = validate_land_record(record)

        self.assertFalse(result["is_valid"])
        self.assertEqual(result["field_results"]["owner_name"]["status"], "invalid")
        self.assertTrue(
            any("unreadable OCR replacement character" in reason for reason in result["field_results"]["owner_name"]["reasons"])
        )
        self.assertEqual(result["normalized_data"]["owner_name"], source_value)

    def test_invalid_area_has_field_level_status_and_reasons(self) -> None:
        result = validate_land_record({**VALID_RECORD, "area": {"value": None, "unit": None}})

        field_result = result["field_results"]["area"]
        self.assertEqual(field_result["status"], "invalid")
        self.assertGreaterEqual(len(field_result["reasons"]), 2)
        self.assertEqual(result["normalized_data"]["area"], {"value": None, "unit": None})

    def test_multiple_simultaneous_errors(self) -> None:
        result = validate_land_record(
            {
                **VALID_RECORD,
                "owner_name": None,
                "khata_number": "bad",
                "area": {"value": "-2", "unit": "bigha"},
            }
        )

        self.assertFalse(result["is_valid"])
        self.assertGreaterEqual(len(result["errors"]), 3)

    def test_warning_only_case(self) -> None:
        record = {
            **VALID_RECORD,
            "owner_name": "A" * 101,
        }

        result = validate_land_record(record)

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertEqual(result["field_results"]["owner_name"]["status"], "warning")

    def test_valid_record_with_optional_data_missing(self) -> None:
        record = {key: value for key, value in VALID_RECORD.items() if key != "original_values"}

        result = validate_land_record(record)

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["errors"], [])

    def test_normalized_data_and_original_values_are_unchanged(self) -> None:
        record = {**VALID_RECORD, "original_values": {"area": "2.50 hectare"}}

        result = validate_land_record(record)

        self.assertEqual(result["normalized_data"], record)
        self.assertEqual(result["normalized_data"]["original_values"], {"area": "2.50 hectare"})
        self.assertIsNot(result["normalized_data"], record)


if __name__ == "__main__":
    unittest.main()
