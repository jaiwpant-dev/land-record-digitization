"""Layer 3: lossless text and word-evidence capture from Tesseract."""

from pathlib import Path

import pytesseract
from PIL import Image, UnidentifiedImageError


# The sample documents are sparse, single-column land records.  Tesseract's
# automatic layout analysis (PSM 3) is the appropriate conservative default;
# spelling it out makes the production behaviour stable across installations.
OCR_LANGUAGE = "eng"
SUPPORTED_OCR_LANGUAGES = {"eng", "ben", "hin"}
PROJECT_TESSDATA_DIR = Path(__file__).resolve().parents[1] / "tessdata"
OCR_CONFIG = "--oem 3 --psm 3"
# A hung OCR process must become a reportable OCR failure instead of blocking a
# record indefinitely.  This applies to both the text and TSV requests.
OCR_TIMEOUT_SECONDS = 60


class OcrProcessingError(RuntimeError):
	"""An OCR failure that retains any raw source text already produced."""

	def __init__(self, message: str, raw_text: str = "") -> None:
		super().__init__(message)
		self.raw_text = raw_text


def _word_confidences(data: dict[str, list[object]]) -> list[dict[str, object]]:
	"""Keep every usable TSV word and its location without changing its text."""
	columns = ("text", "conf", "left", "top", "width", "height", "page_num", "block_num", "par_num", "line_num", "word_num")
	if not all(column in data for column in columns):
		raise OcrProcessingError("Tesseract TSV output is missing required word columns")

	words: list[dict[str, object]] = []
	for row in zip(*(data[column] for column in columns)):
		text, confidence, left, top, width, height, page, block, paragraph, line, word = row
		try:
			confidence_value = float(confidence)
		except (TypeError, ValueError):
			continue
		# Tesseract uses negative confidence for non-word layout rows.  Do not
		# manufacture a confidence for them or include them as word evidence.
		if not isinstance(text, str) or not text.strip() or confidence_value < 0:
			continue
		words.append(
			{
				"text": text,
				"confidence": confidence_value,
				"left": left,
				"top": top,
				"width": width,
				"height": height,
				"page_num": page,
				"block_num": block,
				"par_num": paragraph,
				"line_num": line,
				"word_num": word,
			}
		)
	return words


def _ocr_arguments(language: str) -> tuple[str, str]:
	"""Return an explicitly supported language plus its model location."""
	if language not in SUPPORTED_OCR_LANGUAGES:
		raise ValueError(f"Unsupported OCR language: {language}")
	# Indian-language records retain the established English schema labels.  A
	# combined pass recognizes those labels and script-specific field values.
	return (language, OCR_CONFIG) if language == "eng" else (f"eng+{language}", f"{OCR_CONFIG} --tessdata-dir {PROJECT_TESSDATA_DIR.as_posix()}")


def extract_text_from_image(image_path: str, language: str = OCR_LANGUAGE) -> str:
	"""Extract raw English text from a JPG or PNG image without rewriting it."""
	path = Path(image_path)
	if not path.is_file():
		raise FileNotFoundError(f"Image file does not exist: {path}")

	try:
		with Image.open(path) as image:
			image.load()
			ocr_language, config = _ocr_arguments(language)
			return pytesseract.image_to_string(
				image, lang=ocr_language, config=config, timeout=OCR_TIMEOUT_SECONDS
			)
	except pytesseract.TesseractNotFoundError as exc:
		raise RuntimeError(
			"Tesseract OCR is not available. Install Tesseract and ensure it is on PATH."
		) from exc
	except pytesseract.TesseractError as exc:
		raise RuntimeError(f"Tesseract OCR failed for image: {path}") from exc
	except RuntimeError as exc:
		raise RuntimeError(f"Tesseract OCR timed out or failed for image: {path}") from exc
	except (UnidentifiedImageError, OSError) as exc:
		raise ValueError(f"Unsupported or corrupt image file: {path}") from exc


def extract_ocr_result_from_image(image_path: str, language: str = OCR_LANGUAGE) -> dict[str, object]:
	"""Return unmodified OCR text and Tesseract TSV word-confidence evidence."""
	path = Path(image_path)
	if not path.is_file():
		raise FileNotFoundError(f"Image file does not exist: {path}")

	try:
		with Image.open(path) as image:
			image.load()
			ocr_language, config = _ocr_arguments(language)
			# Preserve the engine's Unicode and whitespace exactly.  The pipeline
			# performs its own non-destructive empty-output check before extraction.
			raw_text = pytesseract.image_to_string(
				image, lang=ocr_language, config=config, timeout=OCR_TIMEOUT_SECONDS
			)
			try:
				data = pytesseract.image_to_data(
					image,
					lang=ocr_language,
					config=config,
					output_type=pytesseract.Output.DICT,
					timeout=OCR_TIMEOUT_SECONDS,
				)
				words = _word_confidences(data)
			except (pytesseract.TesseractError, RuntimeError) as exc:
				# Text is primary source evidence.  Preserve it if TSV generation
				# fails rather than replacing it with an empty string upstream.
				raise OcrProcessingError(
					f"Tesseract TSV confidence extraction failed for image: {path}", raw_text
				) from exc
			return {"raw_text": raw_text, "word_confidences": words}
	except pytesseract.TesseractNotFoundError as exc:
		raise RuntimeError(
			"Tesseract OCR is not available. Install Tesseract and ensure it is on PATH."
		) from exc
	except pytesseract.TesseractError as exc:
		raise RuntimeError(f"Tesseract OCR failed for image: {path}") from exc
	except OcrProcessingError:
		raise
	except RuntimeError as exc:
		raise OcrProcessingError(
			f"Tesseract OCR timed out or failed for image: {path}"
		) from exc
	except (UnidentifiedImageError, OSError) as exc:
		raise ValueError(f"Unsupported or corrupt image file: {path}") from exc
