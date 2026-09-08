"""Layer 4: conservatively extract one land record from raw OCR text.

This layer identifies structure but does not correct OCR. Parsed values stay
as OCR produced them (apart from surrounding line whitespace and the label
separator); normalization and validation own their transformations.
"""

import re


FIELD_LABELS = (
    "Owner Name", "Father Name", "District", "Tehsil", "Village", "Khata No",
    "Khasra No", "Area", "Land Type",
)

# OCR commonly varies case, whitespace and punctuation in labels. These are
# label-only variants; values are never inferred from a fuzzy text match.
_LABEL_PATTERNS = {
    "Owner Name": r"owner[ _\t]+name",
    "Father Name": r"father(?:[’']s)?[ _\t]+name",
    "District": r"district",
    "Tehsil": r"tehsil",
    "Village": r"village",
    "Khata No": r"khata[ _\t]+(?:no|number)\.?",
    "Khasra No": r"khasra[ _\t]+(?:no|number)\.?",
    "Area": r"area",
    "Land Type": r"land[ _\t]+type",
}
_LABEL_RE = re.compile(
    r"^\s*(?P<label>" + "|".join(
        f"(?P<f{index}>{pattern})" for index, pattern in enumerate(_LABEL_PATTERNS.values())
    ) + r")\s*(?:(?P<separator>[:\-–—])\s*(?P<value>.*))?$",
    re.IGNORECASE,
)
_LABEL_BY_GROUP = dict(zip((f"f{index}" for index in range(len(FIELD_LABELS))), FIELD_LABELS))
_IGNORED_TRAILING_LINES = {"fictional demonstration data only"}


def _label_and_inline_value(line: str) -> tuple[str, str | None] | None:
    """Return a recognized label and an explicitly inline value, if any."""
    match = _LABEL_RE.fullmatch(line)
    if match is None:
        return None
    field = next((name for group, name in _LABEL_BY_GROUP.items() if match.group(group) is not None), None)
    if field is None:
        return None
    value = match.group("value")
    return field, value.strip() if value and value.strip() else None


def _raise_missing(found: set[str]) -> None:
    missing = [label for label in FIELD_LABELS if label not in found]
    if missing:
        raise ValueError(f"Missing expected OCR field labels: {', '.join(missing)}")


def _extract_positional_values(entries: list[tuple[str, str | None, int]], lines: list[str]) -> dict[str, str]:
    last_label_index = max(index for _, _, index in entries)
    values = [line for line in lines[last_label_index + 1 :] if line.casefold() not in _IGNORED_TRAILING_LINES]
    if len(values) < len(FIELD_LABELS):
        raise ValueError("OCR text does not contain enough field values")
    return dict(zip(FIELD_LABELS, values[: len(FIELD_LABELS)]))


def _extract_labeled_values(entries: list[tuple[str, str | None, int]], lines: list[str]) -> dict[str, str]:
    """Extract inline or one-line-after-label values without guessing."""
    result: dict[str, str] = {}
    for position, (field, inline_value, index) in enumerate(entries):
        if inline_value is not None:
            result[field] = inline_value
            continue
        next_label = entries[position + 1][2] if position + 1 < len(entries) else len(lines)
        candidates = [line for line in lines[index + 1 : next_label] if line.casefold() not in _IGNORED_TRAILING_LINES]
        if not candidates:
            raise ValueError(f"Missing value for OCR field label: {field}")
        if len(candidates) > 1:
            raise ValueError(f"Ambiguous OCR values for field label: {field}")
        result[field] = candidates[0]
    return result


def extract_land_record_fields(raw_text: str) -> dict[str, str]:
    """Return source values for one explicitly labelled land-record document.

    Supports the baseline label-block layout plus alternating and inline
    ``Label: value`` layouts. Duplicate labels, missing values, and multiple
    candidate values are rejected so extraction cannot silently select one.
    """
    if not isinstance(raw_text, str):
        raise TypeError("Raw OCR text must be a string")
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    entries = [
        (field, value, index)
        for index, line in enumerate(lines)
        if (parsed := _label_and_inline_value(line)) is not None
        for field, value in (parsed,)
    ]
    found = {field for field, _, _ in entries}
    _raise_missing(found)
    if len(entries) != len(FIELD_LABELS):
        duplicates = sorted(field for field in found if sum(item[0] == field for item in entries) > 1)
        raise ValueError(f"Duplicate OCR field labels are ambiguous: {', '.join(duplicates)}")

    has_inline_values = any(value is not None for _, value, _ in entries)
    first_label_index = min(index for _, _, index in entries)
    last_label_index = max(index for _, _, index in entries)
    label_block_is_contiguous = all(
        _label_and_inline_value(line) is not None
        for line in lines[first_label_index : last_label_index + 1]
    )
    if not has_inline_values and label_block_is_contiguous:
        return _extract_positional_values(entries, lines)
    return _extract_labeled_values(entries, lines)
