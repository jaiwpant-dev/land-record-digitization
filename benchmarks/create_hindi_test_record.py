"""Create one controlled, fictional Hindi land-record integration sample."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUTPUT = Path(__file__).resolve().parents[1] / "sample_documents" / "synthetic_hindi_land_record.png"
FONT = Path(r"C:\Windows\Fonts\Nirmala.ttc")


def main() -> None:
    image = Image.new("RGB", (1800, 1320), "#fffdf5")
    draw = ImageDraw.Draw(image)
    title = ImageFont.truetype(str(FONT), 42, index=0)
    text = ImageFont.truetype(str(FONT), 34, index=0)
    draw.rectangle((50, 45, 1750, 1270), outline="#36454f", width=4)
    draw.text((100, 90), "SYNTHETIC HINDI LAND RECORD", fill="#17202a", font=title)
    draw.text((100, 160), "Fictional non-sensitive demonstration data", fill="#34495e", font=text)
    rows = (
        ("Owner Name", "अमित शर्मा"), ("Father Name", "रमेश शर्मा"),
        ("District", "दिल्ली"), ("Tehsil", "विकासनगर"),
        ("Village", "नवगांव"), ("Khata No", "KH-4101"),
        ("Khasra No", "81/2"), ("Area", "1.50 hectare"),
        ("Land Type", "कृषि भूमि"),
    )
    y = 245
    for label, value in rows:
        draw.line((90, y - 12, 1710, y - 12), fill="#aab7b8", width=1)
        draw.text((120, y), f"{label}: {value}", fill="#111111", font=text)
        y += 110
    image.save(OUTPUT, "PNG")


if __name__ == "__main__":
    main()
