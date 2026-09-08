"""Create frozen, fictional land-record images and their benchmark manifest.

The records use invented names and places.  This generator is deliberately
separate from the runner: the runner only reads the committed manifest and
calls the public HTTP API, so no truth values enter the processing path.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent / "data" / "prototype_land_record_test"
FONT = Path(r"C:\Windows\Fonts\Nirmala.ttc")
RECORDS = [
    ("prototype-en-001", "eng", {"owner_name": "Aarav Mehta", "father_name": "Vikram Mehta", "district": "Nainital", "tehsil": "Bhimtal", "village": "Suryagaon", "khata_number": "KH-2101", "khasra_number": "101/2", "area": {"value": "1.25", "unit": "hectare"}, "land_type": "Agricultural"}),
    ("prototype-en-002", "eng", {"owner_name": "Nisha Verma", "father_name": "Mohan Verma", "district": "Almora", "tehsil": "Ranikhet", "village": "Pine Valley", "khata_number": "KH-2102", "khasra_number": "88/3", "area": {"value": "0.75", "unit": "acre"}, "land_type": "Orchard"}),
    ("prototype-en-003", "eng", {"owner_name": "Kabir Singh", "father_name": "Dev Singh", "district": "Pithoragarh", "tehsil": "Didihat", "village": "River Bend", "khata_number": "KH-2103", "khasra_number": "240/1", "area": {"value": "3.00", "unit": "hectare"}, "land_type": "Pasture"}),
    ("prototype-en-004", "eng", {"owner_name": "Ira Shah", "father_name": "Ketan Shah", "district": "Dehradun", "tehsil": "Vikasnagar", "village": "Green Field", "khata_number": "KH-2104", "khasra_number": "19/4", "area": {"value": "450", "unit": "square_meter"}, "land_type": "Residential"}),
]
BENGALI_TEST_RECORD = {"owner_name": "অনির্বাণ দত্ত", "father_name": "বিমল দত্ত", "district": "নদীয়া", "tehsil": "কৃষ্ণনগর", "village": "নবগ্রাম", "khata_number": "KH-3101", "khasra_number": "71/2", "area": {"value": "1.50", "unit": "hectare"}, "land_type": "কৃষিজমি"}


def _area_text(area: dict[str, str]) -> str:
    return {"hectare": "hectare", "acre": "acre", "square_meter": "sq m"}[area["unit"]].join((area["value"] + " ", ""))


def _draw(image_path: Path, values: dict[str, object], *, bengali: bool = False) -> None:
    image = Image.new("RGB", (1800, 1420), "#fffdf5")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(str(FONT), 44, index=0)
    text_font = ImageFont.truetype(str(FONT), 32, index=0)
    draw.rectangle((50, 45, 1750, 1370), outline="#36454f", width=4)
    draw.text((100, 95), "SYNTHETIC LAND RECORD — PROTOTYPE EVALUATION", fill="#17202a", font=title_font)
    draw.text((100, 165), "Fictional non-sensitive demonstration data", fill="#34495e", font=text_font)
    area = values["area"]
    assert isinstance(area, dict)
    rows = [
        ("Owner Name", values["owner_name"]), ("Father Name", values["father_name"]),
        ("District", values["district"]), ("Tehsil", values["tehsil"]),
        ("Village", values["village"]), ("Khata No", values["khata_number"]),
        ("Khasra No", values["khasra_number"]), ("Area", _area_text(area)),
        ("Land Type", values["land_type"]),
    ]
    y = 260
    for label, value in rows:
        draw.line((90, y - 12, 1710, y - 12), fill="#aab7b8", width=1)
        draw.text((120, y), f"{label}: {value}", fill="#111111", font=text_font)
        y += 115
    image.save(image_path, "PNG")


def _ocr_truth(values: dict[str, object]) -> str:
    area = values["area"]
    assert isinstance(area, dict)
    rows = [("Owner Name", values["owner_name"]), ("Father Name", values["father_name"]), ("District", values["district"]), ("Tehsil", values["tehsil"]), ("Village", values["village"]), ("Khata No", values["khata_number"]), ("Khasra No", values["khasra_number"]), ("Area", _area_text(area)), ("Land Type", values["land_type"])]
    return "\n".join(["SYNTHETIC LAND RECORD — PROTOTYPE EVALUATION", "Fictional non-sensitive demonstration data", *(f"{label}: {value}" for label, value in rows)])


def main() -> None:
    images = ROOT / "images"
    images.mkdir(parents=True, exist_ok=True)
    samples = []
    for record_id, language, truth in RECORDS:
        filename = f"{record_id}.png"
        _draw(images / filename, truth)
        samples.append({"id": record_id, "image": f"images/{filename}", "language": language, "ground_truth": truth, "ocr_ground_truth": _ocr_truth(truth),
                        "source_ground_truth": {**{key: value for key, value in truth.items() if key != "area"}, "area": truth["area"]["value"], "area_unit": truth["area"]["unit"]}})
    _draw(Path(__file__).resolve().parents[1] / "sample_documents" / "synthetic_bengali_land_record.png", BENGALI_TEST_RECORD)
    manifest = {"benchmark_type": "field_extraction", "dataset": {"name": "Synthetic land-record prototype baseline", "version": "1", "license": "Repository-created fictional demonstration data", "split": "test", "ground_truth_method": "Frozen values authored before benchmark execution; no ground-truth field is passed to the API.", "selection": "Four representative, programmatically rendered single-record layouts with invented data.", "representativeness": "PROTOTYPE BASELINE ONLY. It is not a government-record or population-accuracy claim."}, "samples": samples}
    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
