"""Deterministic validation for normalized land-record data."""

import copy
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any


REQUIRED_FIELDS = (
    "owner_name",
    "father_name",
    "district",
    "tehsil",
    "village",
    "khata_number",
    "khasra_number",
    "area",
    "land_type",
)
OPTIONAL_FIELDS = ()
VALID_AREA_UNITS = {"hectare", "acre", "square_meter"}
KHASRA_PATTERN = re.compile(r"^(?P<plot>\d+)(?:/(?P<subdivision>\d+))?$")
KHATA_PATTERN = re.compile(r"^KH-(?P<number>\d+)$")


def _field_result() -> dict[str, Any]:
    return {"valid": True, "status": "valid", "errors": [], "warnings": [], "reasons": []}


def _add_error(field_results: dict[str, Any], field: str, message: str) -> None:
    field_results[field]["valid"] = False
    field_results[field]["errors"].append(message)


def _add_warning(field_results: dict[str, Any], field: str, message: str) -> None:
    field_results[field]["warnings"].append(message)


def _validate_text_field(
    data: Mapping[str, Any], field_results: dict[str, Any], field: str, required: bool
) -> None:
    value = data.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            _add_error(field_results, field, f"{field} is required and cannot be empty")
        else:
            _add_warning(field_results, field, f"{field} is missing")
        return
    if not isinstance(value, str):
        _add_error(field_results, field, f"{field} must be a string")
        return
    if not re.search(r"\w", value, re.UNICODE):
        _add_error(field_results, field, f"{field} is obviously malformed")
    if "\ufffd" in value:
        _add_error(field_results, field, f"{field} contains an unreadable OCR replacement character")
    if any(ord(character) < 32 for character in value):
        _add_error(field_results, field, f"{field} contains control characters")
    if len(value) > 100:
        _add_warning(field_results, field, f"{field} is unusually long and should be reviewed")


def _validate_identifier(
    data: Mapping[str, Any],
    field_results: dict[str, Any],
    field: str,
    pattern: re.Pattern[str],
) -> None:
    value = data.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        _add_error(field_results, field, f"{field} is required and cannot be empty")
        return
    if not isinstance(value, str) or not pattern.fullmatch(value):
        _add_error(field_results, field, f"{field} has an invalid format")
        return
    match = pattern.fullmatch(value)
    assert match is not None
    if any(int(part) <= 0 for part in match.groupdict().values() if part is not None):
        _add_error(field_results, field, f"{field} must contain positive identifier components")


def _validate_area(data: Mapping[str, Any], field_results: dict[str, Any]) -> None:
    field = "area"
    area = data.get(field)
    if area is None:
        _add_error(field_results, field, "area is required and cannot be empty")
        return
    if not isinstance(area, Mapping):
        _add_error(field_results, field, "area must contain a numeric value and unit")
        return

    value = area.get("value")
    unit = area.get("unit")
    if value is None or (isinstance(value, str) and not value.strip()):
        _add_error(field_results, field, "area value must be numeric")
    else:
        try:
            numeric_value = Decimal(str(value))
        except (InvalidOperation, ValueError):
            _add_error(field_results, field, "area value must be numeric")
        else:
            if not numeric_value.is_finite():
                _add_error(field_results, field, "area value must be finite")
            elif numeric_value <= 0:
                _add_error(field_results, field, "area must be positive")

    if not isinstance(unit, str) or unit not in VALID_AREA_UNITS:
        _add_error(field_results, field, "area has an unsupported unit")


def _finalize_field_results(fields: dict[str, Any]) -> None:
    """Add stable field statuses/reasons without changing validation evidence."""
    for result in fields.values():
        reasons = [*result["errors"], *result["warnings"]]
        result["reasons"] = reasons
        result["status"] = "invalid" if result["errors"] else "warning" if result["warnings"] else "valid"


def validate_land_record(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate normalized land-record data without changing it."""
    if not isinstance(data, Mapping):
        raise TypeError("Normalized land-record data must be a mapping")

    fields = {field: _field_result() for field in REQUIRED_FIELDS + OPTIONAL_FIELDS}
    for field in ("owner_name", "father_name", "village", "tehsil", "district", "land_type"):
        _validate_text_field(data, fields, field, required=True)
    _validate_identifier(data, fields, "khasra_number", KHASRA_PATTERN)
    _validate_identifier(data, fields, "khata_number", KHATA_PATTERN)
    _validate_area(data, fields)
    _finalize_field_results(fields)

    errors = [
        f"{field}: {message}"
        for field, result in fields.items()
        for message in result["errors"]
    ]
    warnings = [
        f"{field}: {message}"
        for field, result in fields.items()
        for message in result["warnings"]
    ]
    return {
        "is_valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "field_results": fields,
        "normalized_data": copy.deepcopy(dict(data)),
    }
