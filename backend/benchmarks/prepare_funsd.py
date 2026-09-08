"""Download and prepare the official FUNSD test split for generic OCR scoring."""

import argparse
import json
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve


FUNSD_DATASET_URL = "https://guillaumejaume.github.io/FUNSD/"
FUNSD_TERMS_URL = "https://guillaumejaume.github.io/FUNSD/work/"
FUNSD_DOWNLOAD_URL = "https://guillaumejaume.github.io/FUNSD/dataset.zip"


def _transcription(annotation: dict) -> tuple[str, list[str]]:
    """Serialize official word annotations in their supplied entity order.

    FUNSD does not provide a separate page-transcription file. Its original
    JSON annotations contain the text at ``form[*].words[*].text``. Newlines
    retain the supplied entity boundaries; all word strings remain unchanged.
    """
    form = annotation.get("form")
    if not isinstance(form, list):
        raise ValueError("FUNSD annotation is missing a list-valued 'form'")
    lines, words = [], []
    for entity in form:
        if not isinstance(entity, dict) or not isinstance(entity.get("words"), list):
            raise ValueError("FUNSD form entity is missing its words list")
        entity_words = []
        for word in entity["words"]:
            if not isinstance(word, dict) or not isinstance(word.get("text"), str):
                raise ValueError("FUNSD word annotation is missing string text")
            entity_words.append(word["text"])
        if entity_words:
            words.extend(entity_words)
            lines.append(" ".join(entity_words))
    if not words:
        raise ValueError("FUNSD annotation contains no word transcriptions")
    return "\n".join(lines), words


def _find_member(names: list[str], relative_path: str) -> str | None:
    return next((name for name in names if name.casefold().endswith(relative_path.casefold())), None)


def _load_annotation(source: zipfile.ZipFile, annotation_name: str) -> dict:
    """Read official JSON without changing the source bytes copied to disk.

    The archive includes legacy Windows-1252 annotation files (for example,
    a pound sign encoded as byte 0xA3), despite JSON's usual UTF-8 convention.
    """
    payload = source.read(annotation_name)
    for encoding in ("utf-8", "cp1252"):
        try:
            return json.loads(payload.decode(encoding))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"FUNSD annotation cannot be decoded: {annotation_name}")


def prepare(destination: Path, limit: int | None = None) -> Path:
    """Create a manifest from every official FUNSD test page, or a prefix."""
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive when specified")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="funsd-download-") as directory:
        archive = Path(directory) / "dataset.zip"
        urlretrieve(FUNSD_DOWNLOAD_URL, archive)
        with zipfile.ZipFile(archive) as source:
            names = source.namelist()
            annotation_names = sorted(
                name for name in names
                if "/testing_data/annotations/" in name.casefold()
                and name.casefold().endswith(".json")
                and not Path(name).name.startswith(".")
            )
            if not annotation_names:
                raise ValueError("Official FUNSD archive has no testing_data annotations")
            if limit is not None:
                annotation_names = annotation_names[:limit]
            samples = []
            for annotation_name in annotation_names:
                annotation = _load_annotation(source, annotation_name)
                identifier = Path(annotation_name).stem
                image_name = _find_member(names, f"/testing_data/images/{identifier}.png")
                if image_name is None:
                    raise ValueError(f"FUNSD test image is absent for annotation: {annotation_name}")
                ground_truth, words = _transcription(annotation)
                image_target = destination / "images" / Path(image_name).name
                annotation_target = destination / "annotations" / Path(annotation_name).name
                image_target.parent.mkdir(parents=True, exist_ok=True)
                annotation_target.parent.mkdir(parents=True, exist_ok=True)
                image_target.write_bytes(source.read(image_name))
                annotation_target.write_bytes(source.read(annotation_name))
                samples.append({
                    "id": identifier,
                    "image": str(Path("images") / image_target.name),
                    "ground_truth": ground_truth,
                    "ground_truth_words": words,
                    "ground_truth_annotation": str(Path("annotations") / annotation_target.name),
                })
    manifest = {
        "benchmark_type": "generic_ocr",
        "dataset": {
            "name": "FUNSD",
            "language": "English",
            "modality": "real noisy scanned forms",
            "license": "Official FUNSD terms: non-commercial research and educational use only",
            "source_url": FUNSD_DATASET_URL,
            "terms_url": FUNSD_TERMS_URL,
            "download_url": FUNSD_DOWNLOAD_URL,
            "split": "testing_data",
            "ground_truth_source": "Original paired JSON form[*].words[*].text; copied unchanged under annotations/",
            "annotation_decoding": "UTF-8, with Windows-1252 fallback for legacy official JSON; source bytes are copied unchanged.",
            "transcription_serialization": "Words retain supplied text and entity order; words in an entity are space-separated and entities newline-separated.",
            "selection": f"first {len(samples)} annotation filenames in lexical order from official testing_data",
        },
        "samples": samples,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the official FUNSD test split for generic OCR benchmarking.")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    print(prepare(args.destination, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
