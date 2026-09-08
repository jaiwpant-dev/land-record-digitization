"""Explainable field confidence derived from Tesseract word evidence."""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.normalization_service import FIELD_NAMES


HIGH_CONFIDENCE_THRESHOLD = 85.0
MEDIUM_CONFIDENCE_THRESHOLD = 60.0
VALIDATION_MULTIPLIERS = {
    "valid": 1.0,
    "warning": 0.95,
    "invalid": 0.60,
    "unknown": 1.0,
}
# Keep the established ASCII identifier behaviour while treating complete
# Devanagari and Bengali grapheme sequences as words for OCR evidence matching.
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9\u0900-\u097F\u0980-\u09FF]+(?:[./-][A-Za-z0-9\u0900-\u097F\u0980-\u09FF]+)*")


def _tokens(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return [token.casefold() for token in TOKEN_PATTERN.findall(value)]


def _engine_words(ocr_word_confidences: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if ocr_word_confidences is None:
        return []
    if isinstance(ocr_word_confidences, (str, bytes)) or not isinstance(ocr_word_confidences, Sequence):
        raise TypeError("OCR word confidences must be a sequence of mappings or None")

    words: list[dict[str, Any]] = []
    for item in ocr_word_confidences:
        if not isinstance(item, Mapping):
            raise TypeError("Each OCR word confidence must be a mapping")
        text = item.get("text")
        tokens = _tokens(text)
        if not tokens:
            continue
        confidence = item.get("confidence")
        try:
            confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence = None
        if confidence is not None and not 0 <= confidence <= 100:
            confidence = None
        for token in tokens:
            # Keep a copy of the TSV row for field-level explainability.  The
            # confidence layer only derives scores; it never changes OCR
            # evidence supplied by the OCR layer.
            words.append(
                {"token": token, "confidence": confidence, "evidence": dict(item)}
            )
    return words


def _validation_status(validation: Mapping[str, Any] | None, field: str) -> str:
    if not isinstance(validation, Mapping):
        return "unknown"
    field_results = validation.get("field_results")
    if not isinstance(field_results, Mapping):
        return "unknown"
    result = field_results.get(field)
    if not isinstance(result, Mapping):
        return "unknown"
    if not result.get("valid", False):
        return "invalid"
    if result.get("warnings"):
        return "warning"
    return "valid"


def _level(value: float | None) -> str:
    if value is None:
        return "unavailable"
    if value >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    if value >= MEDIUM_CONFIDENCE_THRESHOLD:
        return "medium"
    return "low"


def _overall_confidence(fields: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Return a conservative record score without inventing missing evidence.

    A record score is supportable only when every supported field has a field
    score.  It is the unweighted mean of those scores, capped by the weakest
    field (and therefore also by the weakest invalid field).  The cap prevents
    a set of strong fields from making a partial or invalid record look highly
    reliable.
    """
    unavailable_fields = [
        field for field in FIELD_NAMES if fields[field]["final_confidence"] is None
    ]
    included_fields = [field for field in FIELD_NAMES if field not in unavailable_fields]
    invalid_fields = [
        field for field in included_fields if fields[field]["validation_status"] == "invalid"
    ]
    if unavailable_fields:
        return {
            "confidence": None,
            "confidence_level": "unavailable",
            "included_fields": included_fields,
            "unavailable_fields": unavailable_fields,
            "invalid_fields": invalid_fields,
            "invalid_field_cap": None,
            "weakest_field_cap": None,
        }

    mean = sum(float(fields[field]["final_confidence"]) for field in FIELD_NAMES) / len(FIELD_NAMES)
    invalid_cap = (
        min(float(fields[field]["final_confidence"]) for field in invalid_fields)
        if invalid_fields
        else None
    )
    weakest_field_cap = min(float(fields[field]["final_confidence"]) for field in FIELD_NAMES)
    confidence = min(mean, weakest_field_cap)
    confidence = max(0.0, min(100.0, confidence))
    return {
        "confidence": round(confidence, 2),
        "confidence_level": _level(confidence),
        "included_fields": included_fields,
        "unavailable_fields": [],
        "invalid_fields": invalid_fields,
        "invalid_field_cap": None if invalid_cap is None else round(invalid_cap, 2),
        "weakest_field_cap": round(weakest_field_cap, 2),
    }


def calculate_field_confidence(
    extracted_data: Mapping[str, Any],
    normalized_data: Mapping[str, Any],
    validation: Mapping[str, Any] | None,
    ocr_word_confidences: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Return field confidence from OCR words, match coverage, and validation.

    ``ocr_confidence`` is the character-weighted mean of Tesseract confidence
    values for source-value tokens matched in document order.  ``final_confidence``
    is ``ocr_confidence * confidence_coverage * validation_multiplier``.
    ``confidence_coverage`` counts only source tokens with a usable TSV
    confidence; this prevents unscored matched tokens from inflating a result.
    A missing engine confidence remains unavailable; it is never substituted
    with a guess.
    The overall score is available only when all fields have a final score.
    """
    if not isinstance(extracted_data, Mapping) or not isinstance(normalized_data, Mapping):
        raise TypeError("Extracted and normalized land-record data must be mappings")

    engine_words = _engine_words(ocr_word_confidences)
    originals = normalized_data.get("original_values", {})
    if not isinstance(originals, Mapping):
        originals = {}

    fields: dict[str, Any] = {}
    cursor = 0
    for field in FIELD_NAMES:
        source_value = originals.get(field)
        expected = _tokens(source_value)
        matched: list[dict[str, Any]] = []
        search_cursor = cursor
        for token in expected:
            match_index = next(
                (index for index in range(search_cursor, len(engine_words)) if engine_words[index]["token"] == token),
                None,
            )
            if match_index is None:
                continue
            matched.append(engine_words[match_index])
            search_cursor = match_index + 1
        if matched:
            cursor = search_cursor

        coverage = len(matched) / len(expected) if expected else 0.0
        confident_words = [word for word in matched if word["confidence"] is not None]
        confidence_coverage = len(confident_words) / len(expected) if expected else 0.0
        if confident_words:
            total_weight = sum(len(word["token"]) for word in confident_words)
            ocr_confidence = sum(
                word["confidence"] * len(word["token"]) for word in confident_words
            ) / total_weight
        else:
            ocr_confidence = None

        validation_status = _validation_status(validation, field)
        final_confidence = (
            None
            if ocr_confidence is None
            else ocr_confidence * confidence_coverage * VALIDATION_MULTIPLIERS[validation_status]
        )
        if final_confidence is not None:
            final_confidence = max(0.0, min(100.0, final_confidence))
        normalized_value = normalized_data.get(field)
        fields[field] = {
            "source_value": source_value,
            "normalized_value": normalized_value,
            "normalization_applied": normalized_value != source_value,
            "matched_word_count": len(matched),
            "expected_word_count": len(expected),
            "token_coverage": round(coverage, 4),
            "confidence_coverage": round(confidence_coverage, 4),
            "ocr_confidence": None if ocr_confidence is None else round(ocr_confidence, 2),
            "matched_ocr_words": [dict(word["evidence"]) for word in matched],
            "validation_status": validation_status,
            "validation_multiplier": VALIDATION_MULTIPLIERS[validation_status],
            "final_confidence": None if final_confidence is None else round(final_confidence, 2),
            "confidence_level": _level(final_confidence),
        }

    overall = _overall_confidence(fields)
    return {
        "method": "tesseract_word_confidence_with_coverage_and_validation_v2",
        "formula": {
            "field": "bounded(ocr_confidence * confidence_coverage * validation_multiplier)",
            "ocr_confidence": "character-weighted mean of matched TSV word confidences",
            "overall": "mean of all field scores capped at the weakest field; unavailable if any field score is unavailable",
        },
        "thresholds": {
            "high": HIGH_CONFIDENCE_THRESHOLD,
            "medium": MEDIUM_CONFIDENCE_THRESHOLD,
            "low": 0.0,
        },
        "fields": fields,
        "overall_confidence": overall["confidence"],
        "overall_confidence_level": overall["confidence_level"],
        "overall": overall,
    }
