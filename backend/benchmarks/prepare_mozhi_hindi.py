"""Download and prepare a bounded, reproducible Mozhi-Hindi generic-OCR set."""

import argparse
import json
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve


MOZHI_HINDI_TEST_URL = "https://cdn.iiit.ac.in/cdn/ilocr.iiit.ac.in/public/printed/phase-0/v0.5/hindi/akshara/test.zip"
MOZHI_HINDI_DATASET_URL = "https://ilocr.iiit.ac.in/dataset/7/"


def prepare(destination: Path, limit: int = 100) -> Path:
    """Create a local generic-OCR manifest from the first ``limit`` test rows."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mozhi-hindi-download-") as directory:
        archive = Path(directory) / "test.zip"
        urlretrieve(MOZHI_HINDI_TEST_URL, archive)
        with zipfile.ZipFile(archive) as source:
            names = source.namelist()
            gt_name = next((name for name in names if name.casefold().endswith("test_gt.txt")), None)
            if gt_name is None:
                raise ValueError("Mozhi archive does not contain test_gt.txt")
            rows = source.read(gt_name).decode("utf-8-sig").splitlines()
            samples = []
            for row in rows:
                if len(samples) >= limit:
                    break
                filename, separator, transcription = row.partition("\t")
                if not separator:
                    raise ValueError("Mozhi test_gt.txt has a malformed row")
                image_name = next(
                    (
                        name for name in names
                        if name == filename
                        or name.endswith(f"/{filename}")
                        or Path(name).name == Path(filename).name
                    ),
                    None,
                )
                if image_name is None:
                    raise ValueError(f"Image named by ground truth is absent: {filename}")
                target = destination / "images" / Path(filename).name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read(image_name))
                samples.append({"id": filename, "image": str(Path("images") / Path(filename).name), "ground_truth": transcription})
    manifest = {
        "benchmark_type": "generic_ocr",
        "dataset": {
            "name": "Mozhi-Hindi",
            "language": "Hindi",
            "modality": "printed word images from real scanned pages",
            "license": "CC BY 4.0",
            "source_url": MOZHI_HINDI_DATASET_URL,
            "download_url": MOZHI_HINDI_TEST_URL,
            "split": "test",
            "selection": f"first {len(samples)} rows in provider test_gt.txt order",
        },
        "samples": samples,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a reproducible Mozhi-Hindi test subset.")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    print(prepare(args.destination, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
