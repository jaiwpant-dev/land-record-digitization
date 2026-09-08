"""Normalize extracted land-record fields without discarding source values."""

import re
import unicodedata
from collections.abc import Mapping
from typing import Any


FIELD_ALIASES = {
    "Owner Name": "owner_name",
    "owner_name": "owner_name",
    "Father Name": "father_name",
    "father_name": "father_name",
    "District": "district",
    "district": "district",
    "Tehsil": "tehsil",
    "tehsil": "tehsil",
    "Village": "village",
    "village": "village",
    "Khata No": "khata_number",
    "khata_number": "khata_number",
    "Khasra No": "khasra_number",
    "khasra_number": "khasra_number",
    "Area": "area",
    "area": "area",
    "Land Type": "land_type",
    "land_type": "land_type",
}

# Accept only documented, formatting-equivalent input-key variants. This is
# separate from value normalization: unknown labels still fail safely.
_FIELD_KEY_VARIANTS = {
    "owner name": "owner_name", "owner_name": "owner_name",
    "father name": "father_name", "father's name": "father_name", "father_name": "father_name",
    "district": "district", "tehsil": "tehsil", "village": "village",
    "khata no": "khata_number", "khata no.": "khata_number",
    "khata number": "khata_number", "khata_number": "khata_number",
    "khasra no": "khasra_number", "khasra no.": "khasra_number",
    "khasra number": "khasra_number", "khasra_number": "khasra_number",
    "area": "area", "land type": "land_type", "land_type": "land_type",
}

FIELD_NAMES = (
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

AREA_UNITS = {
    "ha": "hectare",
    "hectare": "hectare",
    "hectares": "hectare",
    "acre": "acre",
    "acres": "acre",
    "sqm": "square_meter",
    "sq m": "square_meter",
    "square meter": "square_meter",
    "square meters": "square_meter",
}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Land-record field values must be strings or None")
    cleaned = " ".join(unicodedata.normalize("NFC", value).split())
    return cleaned or None


def _normalize_identifier(value: Any) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    return re.sub(r"\s*([/-])\s*", r"\1", cleaned).upper()


def _normalize_area(value: Any) -> tuple[dict[str, str | None] | None, bool]:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None, False

    match = re.fullmatch(
        r"(?P<number>\d+(?:\.\d+|,\d{1,2})?)\s*(?P<unit>[A-Za-z. ]+)", cleaned
    )
    if not match:
        return {"value": None, "unit": None}, False

    unit_key = re.sub(r"\s*\.\s*", " ", match.group("unit")).strip().lower()
    unit = AREA_UNITS.get(unit_key)
    if unit is None:
        return {"value": None, "unit": None}, False

    number = match.group("number").replace(",", ".")
    return {"value": number, "unit": unit}, True


def _canonical_field_name(key: Any) -> str | None:
    if not isinstance(key, str):
        return None
    normalized_key = " ".join(unicodedata.normalize("NFC", key).split()).casefold()
    return FIELD_ALIASES.get(key) or _FIELD_KEY_VARIANTS.get(normalized_key)


def normalize_land_record(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return predictable normalized fields and preserve every source value."""
    if not isinstance(data, Mapping):
        raise TypeError("Extracted land-record data must be a mapping")

    source_values = {field: None for field in FIELD_NAMES}
    supplied_fields: set[str] = set()
    for key, value in data.items():
        field_name = _canonical_field_name(key)
        if field_name is None:
            raise ValueError(f"Unknown land-record field: {key}")
        if field_name in supplied_fields:
            raise ValueError(f"Duplicate source values for land-record field: {field_name}")
        source_values[field_name] = value
        supplied_fields.add(field_name)

    text_fields = ("owner_name", "father_name", "district", "tehsil", "village", "land_type")
    normalized_text = {field: _clean_text(source_values[field]) for field in text_fields}
    normalized_khata = _normalize_identifier(source_values["khata_number"])
    normalized_khasra = _normalize_identifier(source_values["khasra_number"])
    normalized_area, area_normalized = _normalize_area(source_values["area"])

    normalized: dict[str, Any] = {
        **normalized_text,
        "khata_number": normalized_khata,
        "khasra_number": normalized_khasra,
        "area": normalized_area,
        "original_values": dict(source_values),
        "normalization_applied": {
            **{field: normalized_text[field] != source_values[field] for field in text_fields},
            "khata_number": normalized_khata != source_values["khata_number"],
            "khasra_number": normalized_khasra != source_values["khasra_number"],
            "area": area_normalized,
        },
    }
    return normalized
