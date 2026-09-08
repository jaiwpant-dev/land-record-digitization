# Intelligent Land Record Digitization & Validation System

Land-record OCR baseline using Tesseract.

## Scope

The implemented single-record pipeline is:

```
document ingestion -> Tesseract raw text + word confidence -> strict field extraction -> normalization -> validation -> field confidence
```

`app.services.ocr_pipeline_service.process_land_record_image()` is the
integration entry point. Its result retains `raw_ocr_text`, the extracted
source fields, normalized fields (including `original_values`), and separate
validation findings, raw word-confidence evidence, and derived field confidence.
Invalid or incomplete data is returned as a structured
failure/review result; it is never repaired silently.

Field confidence is explainable: it uses the character-weighted mean of
matched Tesseract TSV word confidences, multiplied by the fraction of
source-value tokens with usable TSV confidence matched in order, then by a
validation multiplier (1.00 valid, 0.95 warning, 0.60 invalid). Scores are
bounded to 0-100 and missing TSV confidence remains unavailable rather than
being guessed. Each field
retains its matched TSV word rows. The record score is available only if every
supported field has a score; it is the mean of field scores capped by the
weakest field, so partial or invalid fields cannot make a record appear highly
reliable. Levels are high at 85+, medium at
60–84.99, and low below 60.

Dependencies:

- `pytesseract`
- `Pillow`
- `pdf2image`

The OCR pipeline remains separate from persistence.  The FastAPI record API
can persist records independently through Supabase/PostgreSQL; it does not call
or alter OCR processing.

## FastAPI record persistence

Apply [`supabase/migrations/0001_create_land_records.sql`](supabase/migrations/0001_create_land_records.sql)
to the target Supabase project, then configure `SUPABASE_URL` and the
server-only `SUPABASE_SERVICE_ROLE_KEY` (see `.env.example`). The API uses the
Supabase PostgREST endpoint through an adapter/repository layer; no database
queries live in routes.

For production, enter `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and the
comma-separated `LAND_RECORD_API_CORS_ORIGINS` in the hosting platform's secret
or environment settings. Do not commit `.env`. Start the ASGI application with
the platform port and public interface, for example:

```powershell
uvicorn api.main:app --host 0.0.0.0 --port $env:PORT
```

The independent persistence endpoints are:

- `POST /api/v1/records` — create a land record
- `GET /api/v1/records` — list records (`limit`, `offset`)
- `GET /api/v1/records/{record_id}` — retrieve one record
- `PATCH /api/v1/records/{record_id}` — update record fields

Records include document URLs, ownership and location fields, land identifiers
and area, plus validation, confidence, and processing-state data. Missing
Supabase configuration returns `503`; absent records return `404`.

## HTTP API

The Flask application factory is `app.api:create_app`. Start it with:

```powershell
flask --app app.api run
```

`POST /api/v1/land-records/ocr` accepts `multipart/form-data` with a required
`document` file field. PNG, JPG, and JPEG uploads enter the existing full
document pipeline: ingestion, CV preprocessing, OCR, extraction,
normalization, validation, and confidence scoring. The JSON response is the
existing structured pipeline result, including OCR word evidence, validation
field reasons, normalized `original_values`, field confidence, and overall
confidence. The API removes the internal temporary `source_path` and reports
the submitted filename instead.

Successful complete processing returns `200`; validation review results return
`422`; malformed/empty/unsupported uploads return `400`; an upload over the
limit returns `413`; and OCR failures return `502`. Uploaded bytes are streamed
into a per-request temporary directory and deleted after processing. CORS is
not enabled because no frontend origin is currently configured. Set
`LAND_RECORD_MAX_UPLOAD_BYTES` only to impose a stricter limit than the
existing 20 MiB ingestion limit.

## Document ingestion

`app.services.document_ingestion_service.ingest_document()` is Layer 1. It
accepts local JPG, JPEG, and PNG files up to 20 MiB, verifies that the file is
regular, non-empty, readable, and has an extension matching its file signature.
It returns metadata only and never copies or modifies document bytes.

`app.services.ocr_pipeline_service.process_land_record_document()` is the
document-level entry point; it performs ingestion, then conservative CV
preprocessing, before the existing image OCR pipeline. PDF ingestion is intentionally unsupported because the current OCR
pipeline accepts a single image only; PDF rendering and multi-page handling are
future work, not CV preprocessing in this layer.

## CV preprocessing

`app.services.preprocessing_service.preprocess_image()` creates a temporary
PNG derivative and leaves the ingested source byte-for-byte unchanged. It
always applies grayscale and conditionally applies EXIF orientation correction,
upscaling below 1200 pixels wide, isolated impulse-noise removal, contrast
enhancement, Otsu binarization, and a conservative projection-based deskew.
The document pipeline deletes the temporary derivative after OCR and returns
only preprocessing metadata.
