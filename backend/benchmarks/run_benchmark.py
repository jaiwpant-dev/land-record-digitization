"""Run schema-compatible labeled images through the public OCR HTTP endpoint.

Ground truth is deliberately supplied in a manifest, never inferred from OCR
output.  This keeps benchmark results reproducible and prevents a test runner
from becoming another extraction or normalization layer.
"""

import argparse
import json
import mimetypes
import os
import re
import unicodedata
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg"}
DEFAULT_ENDPOINT = "http://127.0.0.1:5000/api/v1/land-records/ocr"


def _value_text(value: Any) -> str:
    """Stable text representation used only for string-distance metrics."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def levenshtein_distance(left: str, right: str) -> int:
    """Return a dependency-free Levenshtein edit distance."""
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1] + (left_character != right_character),
            ))
        previous = current
    return previous[-1]


def _evaluation_normalize(value: Any) -> Any:
    """Apply documented comparison-only normalization, never pipeline repair.

    Strings are NFKC-normalized, case-folded, stripped, and have whitespace
    collapsed. Dictionaries and lists retain their structure while applying the
    same operation to contained values. No characters, punctuation, numeric
    digits, units, or identifiers are inferred, removed, or substituted.
    """
    if isinstance(value, str):
        return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()
    if isinstance(value, dict):
        return {key: _evaluation_normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_evaluation_normalize(item) for item in value]
    return value


def word_error_distance(left: str, right: str) -> int:
    """Return Levenshtein distance over whitespace-delimited tokens."""
    return levenshtein_distance(left.split(), right.split())


def _post_image(endpoint: str, image_path: Path, timeout_seconds: float, language: str = "eng") -> tuple[int, dict[str, Any]]:
    """Send one image as the API's documented multipart ``document`` field."""
    boundary = f"----landrecordbenchmark{uuid.uuid4().hex}"
    media_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    body = b"".join((
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="document"; filename="{image_path.name}"\r\n'.encode(),
        f"Content-Type: {media_type}\r\n\r\n".encode(),
        image_path.read_bytes(),
        f"\r\n--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="language"\r\n\r\n',
        language.encode("ascii"),
        f"\r\n--{boundary}--\r\n".encode(),
    ))
    request = Request(endpoint, data=body, method="POST", headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            return error.code, json.loads(error.read().decode("utf-8"))
        finally:
            error.close()
    except (URLError, TimeoutError) as error:
        return 0, {"status": "transport_error", "errors": [{"stage": "benchmark", "message": str(error)}]}


def _score_field_extraction_sample(sample: dict[str, Any], response: dict[str, Any], http_status: int) -> dict[str, Any]:
    expected = sample["ground_truth"]
    normalized = response.get("normalized_data") if isinstance(response.get("normalized_data"), dict) else {}
    validation = response.get("validation") if isinstance(response.get("validation"), dict) else {}
    validation_fields = validation.get("field_results") if isinstance(validation.get("field_results"), dict) else {}
    fields: dict[str, Any] = {}
    for field, expected_value in expected.items():
        prediction = normalized.get(field)
        expected_text, prediction_text = _value_text(expected_value), _value_text(prediction)
        distance = levenshtein_distance(expected_text, prediction_text)
        expected_words = _evaluation_normalize(expected_text)
        prediction_words = _evaluation_normalize(prediction_text)
        fields[field] = {
            "expected": expected_value,
            "predicted": prediction,
            "raw_exact_match": prediction == expected_value,
            "normalized_match": _evaluation_normalize(prediction) == _evaluation_normalize(expected_value),
            "missing": prediction is None,
            "character_errors": distance,
            "reference_characters": len(expected_text),
            "word_errors": word_error_distance(expected_words, prediction_words),
            "reference_words": len(expected_words.split()),
            "validation_errors": list((validation_fields.get(field) or {}).get("errors") or []),
        }
    raw_ocr = response.get("raw_ocr_text") if isinstance(response.get("raw_ocr_text"), str) else ""
    ocr_truth = sample.get("ocr_ground_truth")
    ocr_quality = None
    if isinstance(ocr_truth, str):
        ocr_prediction = raw_ocr.strip()
        ocr_quality = {
            "expected": ocr_truth,
            "predicted": ocr_prediction,
            "character_errors": levenshtein_distance(ocr_truth, ocr_prediction),
            "reference_characters": len(ocr_truth),
            "word_errors": word_error_distance(_evaluation_normalize(ocr_truth), _evaluation_normalize(ocr_prediction)),
            "reference_words": len(_evaluation_normalize(ocr_truth).split()),
        }
    return {
        "id": sample["id"],
        "image": sample["image"],
        "http_status": http_status,
        "pipeline_status": response.get("status"),
        "ocr_text_available": bool(response.get("raw_ocr_text")),
        "extraction_success": isinstance(response.get("extracted_data"), dict),
        "ocr_quality": ocr_quality,
        "fields": fields,
        "pipeline_errors": response.get("errors", []),
    }


def _score_generic_ocr_sample(sample: dict[str, Any], response: dict[str, Any], http_status: int) -> dict[str, Any]:
    """Score a word/line transcription without implying field extraction."""
    expected = sample["ground_truth"]
    prediction = response.get("raw_ocr_text")
    prediction = prediction.strip() if isinstance(prediction, str) else ""
    distance = levenshtein_distance(expected, prediction)
    return {
        "id": sample["id"],
        "image": sample["image"],
        "http_status": http_status,
        "pipeline_status": response.get("status"),
        # A response such as 422 (expected when a word crop cannot satisfy the
        # land-record schema) is useful benchmark evidence, but it is not a
        # successful API request.  Keep the two facts separate in the report.
        "http_response_received": http_status > 0,
        "http_request_success": 200 <= http_status < 300,
        "ocr_text_available": bool(prediction),
        "ground_truth": expected,
        "prediction": prediction,
        "exact_match": prediction == expected,
        "character_errors": distance,
        "reference_characters": len(expected),
        "pipeline_errors": response.get("errors", []),
    }


def _aggregate_field_extraction(dataset: dict[str, Any], results: list[dict[str, Any]], skipped: list[dict[str, str]]) -> dict[str, Any]:
    per_field: dict[str, dict[str, int]] = defaultdict(lambda: {
        "evaluated": 0, "raw_exact_matches": 0, "normalized_matches": 0,
        "missing": 0, "character_errors": 0, "reference_characters": 0,
        "word_errors": 0, "reference_words": 0, "validation_error_count": 0,
    })
    statuses = Counter()
    requests = Counter()
    raw_record_matches = normalized_record_matches = 0
    for result in results:
        statuses[str(result["pipeline_status"])] += 1
        requests[str(result["http_status"])] += 1
        field_scores = list(result["fields"].values())
        raw_record_matches += bool(field_scores) and all(score["raw_exact_match"] for score in field_scores)
        normalized_record_matches += bool(field_scores) and all(score["normalized_match"] for score in field_scores)
        for field, score in result["fields"].items():
            metrics = per_field[field]
            metrics["evaluated"] += 1
            metrics["raw_exact_matches"] += int(score["raw_exact_match"])
            metrics["normalized_matches"] += int(score["normalized_match"])
            metrics["missing"] += int(score["missing"])
            metrics["character_errors"] += score["character_errors"]
            metrics["reference_characters"] += score["reference_characters"]
            metrics["word_errors"] += score["word_errors"]
            metrics["reference_words"] += score["reference_words"]
            metrics["validation_error_count"] += len(score["validation_errors"])
    fields = {
        field: {
            **metrics,
            "raw_exact_match_rate": None if not metrics["evaluated"] else round(metrics["raw_exact_matches"] / metrics["evaluated"], 6),
            "normalized_match_rate": None if not metrics["evaluated"] else round(metrics["normalized_matches"] / metrics["evaluated"], 6),
            "missing_field_rate": None if not metrics["evaluated"] else round(metrics["missing"] / metrics["evaluated"], 6),
            "character_error_rate": None if not metrics["reference_characters"] else round(metrics["character_errors"] / metrics["reference_characters"], 6),
            "word_error_rate": None if not metrics["reference_words"] else round(metrics["word_errors"] / metrics["reference_words"], 6),
        }
        for field, metrics in sorted(per_field.items())
    }
    total_evaluated = sum(metrics["evaluated"] for metrics in per_field.values())
    total_raw_exact = sum(metrics["raw_exact_matches"] for metrics in per_field.values())
    total_normalized = sum(metrics["normalized_matches"] for metrics in per_field.values())
    total_missing = sum(metrics["missing"] for metrics in per_field.values())
    metric_fields = list(fields.values())
    complete_extractions = sum(item["extraction_success"] for item in results)
    ocr_scored = [item["ocr_quality"] for item in results if item["ocr_quality"] is not None]
    ocr_character_errors = sum(item["character_errors"] for item in ocr_scored)
    ocr_reference_characters = sum(item["reference_characters"] for item in ocr_scored)
    ocr_word_errors = sum(item["word_errors"] for item in ocr_scored)
    ocr_reference_words = sum(item["reference_words"] for item in ocr_scored)
    return {
        "dataset": dataset,
        "benchmark_type": "field_extraction",
        "evaluated_images": len(results),
        "skipped_images": skipped,
        "http_responses_received": sum(result["http_status"] > 0 for result in results),
        "transport_failures": sum(result["http_status"] == 0 for result in results),
        "successful_http_requests": sum(200 <= result["http_status"] < 300 for result in results),
        "failed_http_requests": sum(not (200 <= result["http_status"] < 300) for result in results),
        "extraction_success_rate": None if not results else round(complete_extractions / len(results), 6),
        "complete_extraction_rate": None if not results else round(complete_extractions / len(results), 6),
        "ocr_text_available": sum(item["ocr_text_available"] for item in results),
        "ocr_text_unavailable": sum(not item["ocr_text_available"] for item in results),
        "pipeline_failure_count": sum(item["pipeline_status"] == "failed" for item in results),
        "non_complete_pipeline_results": sum(item["pipeline_status"] != "complete" for item in results),
        "macro_average_raw_exact_match_rate": None if not metric_fields else round(sum(item["raw_exact_match_rate"] for item in metric_fields) / len(metric_fields), 6),
        "macro_average_normalized_match_rate": None if not metric_fields else round(sum(item["normalized_match_rate"] for item in metric_fields) / len(metric_fields), 6),
        "micro_average_raw_exact_match_rate": None if not total_evaluated else round(total_raw_exact / total_evaluated, 6),
        "micro_average_normalized_match_rate": None if not total_evaluated else round(total_normalized / total_evaluated, 6),
        "overall_land_record_extraction_accuracy": None if not total_evaluated else round(total_normalized / total_evaluated, 6),
        "overall_land_record_extraction_accuracy_definition": "Micro-average normalized field match across required land-record fields; this is not OCR CER.",
        "missing_field_rate": None if not total_evaluated else round(total_missing / total_evaluated, 6),
        "record_raw_exact_match_rate": None if not results else round(raw_record_matches / len(results), 6),
        "record_normalized_match_rate": None if not results else round(normalized_record_matches / len(results), 6),
        "pipeline_status_counts": dict(sorted(statuses.items())),
        "http_status_counts": dict(sorted(requests.items())),
        "evaluation_normalization": "NFKC, case-folding, trimming, and whitespace collapse only; it performs no punctuation, digit, unit, or value correction.",
        "ocr_quality": {
            "scored_images": len(ocr_scored),
            "character_errors": ocr_character_errors,
            "reference_characters": ocr_reference_characters,
            "character_error_rate": None if not ocr_reference_characters else round(ocr_character_errors / ocr_reference_characters, 6),
            "word_errors": ocr_word_errors,
            "reference_words": ocr_reference_words,
            "word_error_rate": None if not ocr_reference_words else round(ocr_word_errors / ocr_reference_words, 6),
            "note": "Raw OCR text transcription quality, scored separately from field extraction.",
        },
        "field_metrics": fields,
        "samples": results,
    }


def _aggregate_generic_ocr(dataset: dict[str, Any], results: list[dict[str, Any]], skipped: list[dict[str, str]]) -> dict[str, Any]:
    statuses = Counter(str(result["pipeline_status"]) for result in results)
    requests = Counter(str(result["http_status"]) for result in results)
    reference_characters = sum(result["reference_characters"] for result in results)
    character_errors = sum(result["character_errors"] for result in results)
    return {
        "dataset": dataset,
        "benchmark_type": "generic_ocr",
        "evaluated_images": len(results),
        "skipped_images": skipped,
        "http_responses_received": sum(result["http_response_received"] for result in results),
        "transport_failures": sum(not result["http_response_received"] for result in results),
        "successful_http_requests": sum(result["http_request_success"] for result in results),
        "failed_http_requests": sum(not result["http_request_success"] for result in results),
        "ocr_text_available": sum(result["ocr_text_available"] for result in results),
        "ocr_text_unavailable": sum(not result["ocr_text_available"] for result in results),
        "exact_matches": sum(result["exact_match"] for result in results),
        "exact_match_rate": None if not results else round(sum(result["exact_match"] for result in results) / len(results), 6),
        "character_errors": character_errors,
        "reference_characters": reference_characters,
        "character_error_rate": None if not reference_characters else round(character_errors / reference_characters, 6),
        "http_status_counts": dict(sorted(requests.items())),
        "pipeline_status_counts": dict(sorted(statuses.items())),
        "land_record_field_extraction_accuracy": None,
        "land_record_field_extraction_note": "Not applicable: this is a generic word/line OCR dataset, not a labeled land-record field dataset.",
        "samples": results,
    }


def run(manifest_path: Path, endpoint: str, timeout_seconds: float) -> dict[str, Any]:
    """Run every existing PNG/JPG/JPEG manifest image against the endpoint."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest.get("dataset"), dict) or not isinstance(manifest.get("samples"), list):
        raise ValueError("Manifest requires object keys 'dataset' and 'samples'")
    benchmark_type = manifest.get("benchmark_type", "field_extraction")
    if benchmark_type not in {"field_extraction", "generic_ocr"}:
        raise ValueError("benchmark_type must be 'field_extraction' or 'generic_ocr'")
    root = manifest_path.parent
    results, skipped = [], []
    for sample in manifest["samples"]:
        expected_type = str if benchmark_type == "generic_ocr" else dict
        if not isinstance(sample, dict) or not isinstance(sample.get("id"), str) or not isinstance(sample.get("image"), str) or not isinstance(sample.get("ground_truth"), expected_type):
            raise ValueError(f"Each {benchmark_type} sample requires string id/image and {expected_type.__name__} ground_truth")
        image = (root / sample["image"]).resolve()
        if image.suffix.casefold() not in SUPPORTED_SUFFIXES:
            skipped.append({"id": sample["id"], "reason": "unsupported_image_extension"})
            continue
        if not image.is_file():
            skipped.append({"id": sample["id"], "reason": "image_not_found"})
            continue
        language = sample.get("language", "eng")
        if not isinstance(language, str):
            raise ValueError("Sample language must be a string when supplied")
        http_status, response = _post_image(endpoint, image, timeout_seconds, language)
        results.append(
            _score_generic_ocr_sample(sample, response, http_status)
            if benchmark_type == "generic_ocr"
            else _score_field_extraction_sample(sample, response, http_status)
        )
    return (
        _aggregate_generic_ocr(manifest["dataset"], results, skipped)
        if benchmark_type == "generic_ocr"
        else _aggregate_field_extraction(manifest["dataset"], results, skipped)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark the public land-record OCR API from a ground-truth manifest.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--endpoint", default=os.getenv("LAND_RECORD_API_URL", DEFAULT_ENDPOINT))
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.manifest, args.endpoint, args.timeout)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_keys = (
        "evaluated_images", "skipped_images", "exact_match_rate", "character_error_rate",
        "extraction_success_rate", "macro_average_raw_exact_match_rate",
        "macro_average_normalized_match_rate", "record_normalized_match_rate",
        "pipeline_status_counts",
    )
    print(json.dumps({key: report[key] for key in summary_keys if key in report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
