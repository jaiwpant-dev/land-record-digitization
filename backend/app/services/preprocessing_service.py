"""Layer 2: conservative, non-destructive image preparation for OCR."""

import math
import os
import tempfile
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError
except ImportError:  # Allows non-image pipeline stages to run without Pillow installed.
    Image = ImageFilter = ImageOps = ImageStat = None
    UnidentifiedImageError = OSError


MIN_OCR_WIDTH = 1200
MAX_UPSCALE_FACTOR = 2.0
LOW_CONTRAST_STANDARD_DEVIATION = 35.0
IMPULSE_NOISE_RATIO = 0.02
MAX_DESKEW_DEGREES = 5.0
DESKEW_STEP_DEGREES = 0.5
DESKEW_IMPROVEMENT_RATIO = 1.12


def _require_pillow() -> None:
    if Image is None:
        raise RuntimeError("Image preprocessing requires Pillow. Install project dependencies.")


def _quality_metrics(grayscale: Any) -> dict[str, float | int]:
    stat = ImageStat.Stat(grayscale)
    histogram = grayscale.histogram()
    pixels = grayscale.width * grayscale.height
    return {
        "width": grayscale.width,
        "height": grayscale.height,
        "mean_luminance": round(stat.mean[0], 2),
        "contrast_standard_deviation": round(stat.stddev[0], 2),
        "dynamic_range": next((255 - index for index, count in enumerate(histogram) if count), 0)
        - next((index for index, count in enumerate(histogram) if count), 255),
        "pixel_count": pixels,
    }


def _otsu_threshold(grayscale: Any) -> int:
    histogram = grayscale.histogram()
    total = sum(histogram)
    total_sum = sum(index * count for index, count in enumerate(histogram))
    background_weight = background_sum = best_variance = 0.0
    threshold = 127
    for index, count in enumerate(histogram):
        background_weight += count
        if not background_weight:
            continue
        foreground_weight = total - background_weight
        if not foreground_weight:
            break
        background_sum += index * count
        background_mean = background_sum / background_weight
        foreground_mean = (total_sum - background_sum) / foreground_weight
        variance = background_weight * foreground_weight * (background_mean - foreground_mean) ** 2
        if variance > best_variance:
            best_variance = variance
            threshold = index
    return threshold


def _impulse_noise_ratio(grayscale: Any) -> float:
    """Estimate isolated black/white pixels on a bounded analysis image."""
    analysis = grayscale.copy()
    analysis.thumbnail((500, 500))
    pixels = analysis.load()
    noisy = checked = 0
    for y in range(1, analysis.height - 1):
        for x in range(1, analysis.width - 1):
            value = pixels[x, y]
            if value not in (0, 255):
                continue
            neighbours = [pixels[x - 1, y], pixels[x + 1, y], pixels[x, y - 1], pixels[x, y + 1]]
            if all(abs(value - neighbour) > 100 for neighbour in neighbours):
                noisy += 1
            checked += 1
    return noisy / max(checked, 1)


def _projection_score(binary: Any) -> float:
    pixels = binary.load()
    row_counts = [sum(pixels[x, y] < 128 for x in range(binary.width)) for y in range(binary.height)]
    average = sum(row_counts) / max(len(row_counts), 1)
    return sum((count - average) ** 2 for count in row_counts)


def _estimate_deskew_angle(grayscale: Any) -> float | None:
    """Return a conservative projection-profile correction angle, if justified."""
    analysis = grayscale.copy()
    analysis.thumbnail((800, 800))
    threshold = _otsu_threshold(analysis)
    binary = analysis.point(lambda pixel: 0 if pixel < threshold else 255)
    baseline = _projection_score(binary)
    if baseline <= 0:
        return None
    best_angle, best_score = 0.0, baseline
    steps = int(MAX_DESKEW_DEGREES / DESKEW_STEP_DEGREES)
    for step in range(-steps, steps + 1):
        angle = step * DESKEW_STEP_DEGREES
        if angle == 0:
            continue
        rotated = binary.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=255)
        score = _projection_score(rotated)
        if score > best_score:
            best_angle, best_score = angle, score
    if abs(best_angle) < DESKEW_STEP_DEGREES or best_score / baseline < DESKEW_IMPROVEMENT_RATIO:
        return None
    return best_angle


def preprocess_image(image_path: str | Path) -> dict[str, Any]:
    """Create an OCR derivative PNG while retaining the source image untouched."""
    _require_pillow()
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image file does not exist: {path}")

    try:
        with Image.open(path) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            image = image.convert("L")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Unsupported or corrupt image file: {path}") from exc

    operations: list[dict[str, Any]] = [{"name": "grayscale", "applied": True}]
    if image.size != source.size:
        operations.append({"name": "exif_orientation", "applied": True})

    before_quality = _quality_metrics(image)
    if image.width < MIN_OCR_WIDTH:
        factor = min(MAX_UPSCALE_FACTOR, MIN_OCR_WIDTH / image.width)
        image = image.resize(
            (round(image.width * factor), round(image.height * factor)), Image.Resampling.LANCZOS
        )
        operations.append({"name": "upscale", "applied": True, "factor": round(factor, 2)})

    if _impulse_noise_ratio(image) >= IMPULSE_NOISE_RATIO:
        image = image.filter(ImageFilter.MedianFilter(size=3))
        operations.append({"name": "median_denoise", "applied": True})

    quality = _quality_metrics(image)
    if quality["contrast_standard_deviation"] < LOW_CONTRAST_STANDARD_DEVIATION:
        original_dynamic_range = quality["dynamic_range"]
        image = ImageOps.autocontrast(image, cutoff=1)
        operations.append({"name": "autocontrast", "applied": True})
        quality = _quality_metrics(image)
        if original_dynamic_range < 100:
            threshold = _otsu_threshold(image)
            image = image.point(lambda pixel: 0 if pixel < threshold else 255)
            operations.append({"name": "otsu_binarization", "applied": True, "threshold": threshold})

    deskew_angle = _estimate_deskew_angle(image)
    if deskew_angle is not None:
        image = image.rotate(deskew_angle, resample=Image.Resampling.BICUBIC, fillcolor=255)
        operations.append({"name": "deskew", "applied": True, "angle_degrees": deskew_angle})

    descriptor, processed_path = tempfile.mkstemp(prefix="land-record-ocr-", suffix=".png")
    os.close(descriptor)
    try:
        image.save(processed_path, format="PNG", optimize=True)
    except OSError:
        Path(processed_path).unlink(missing_ok=True)
        raise

    return {
        "processed_path": processed_path,
        "source_path": str(path.resolve()),
        "source_quality": before_quality,
        "processed_quality": _quality_metrics(image),
        "operations": operations,
    }
