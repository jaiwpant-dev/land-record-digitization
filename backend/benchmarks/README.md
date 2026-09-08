# OCR benchmark runner

`run_benchmark.py` sends every present PNG/JPG/JPEG listed in a ground-truth
manifest to `POST /api/v1/land-records/ocr`. It does not import, call, or alter
any OCR-pipeline service directly.

The default `field_extraction` manifest must use the API's normalized field
names and already-normalized ground truth. A minimal sample is:

```json
{
  "dataset": {
    "name": "Example dataset",
    "license": "CC BY 4.0",
    "source_url": "https://example.org/dataset",
    "version": "1"
  },
  "samples": [{
    "id": "record-001",
    "image": "images/record-001.png",
    "ground_truth": {
      "owner_name": "Example Owner",
      "father_name": "Example Father",
      "district": "Example District",
      "tehsil": "Example Tehsil",
      "village": "Example Village",
      "khata_number": "KH-1",
      "khasra_number": "1/2",
      "area": {"value": "2.50", "unit": "hectare"},
      "land_type": "Agricultural"
    }
  }]
}
```

Start the API, then run:

```powershell
python -m benchmarks.run_benchmark path/to/manifest.json --report reports/benchmark.json
```

The JSON report includes per-field exact-match rate, character error rate
(Levenshtein edits divided by ground-truth characters), validation-error count,
extraction-success rate, HTTP/pipeline results, and skipped images. It never
labels a score as OCR accuracy without ground truth.

For `field_extraction` manifests, the report also provides raw exact match,
comparison-only normalized match, CER, WER, missing-field rate, macro and
micro field accuracy, raw and normalized record exact-match rates, complete
extraction rate, and HTTP/pipeline outcome counts. Evaluation normalization is
limited to NFKC, case folding, trimming, and whitespace collapse; it never
repairs punctuation, identifiers, digits, units, or values.

For word/line data such as Mozhi-Hindi, use `"benchmark_type": "generic_ocr"`
and make each `ground_truth` a string. This compares the API's preserved
`raw_ocr_text` (with only surrounding response whitespace removed) to the
provider transcription. It reports generic OCR exact match and CER, successful
(2xx) versus failed HTTP requests, received HTTP responses versus transport
failures, OCR-text availability, and pipeline-status counts. It explicitly
sets land-record field-extraction accuracy to `null`.

## Mozhi-Hindi preparation

The IIIT [Mozhi-Hindi dataset card](https://ilocr.iiit.ac.in/dataset/7/) states
that the word crops are from real 600-DPI flatbed-scanned book pages, manually
transcribed, and distributed under CC BY 4.0. Its test split has 10,173 word
images. The preparer downloads the official archive, retains the provider's
transcriptions unchanged, and deterministically selects the first 100 test rows
by default (adjust with `--limit`):

```powershell
python -m benchmarks.prepare_mozhi_hindi benchmarks/data/mozhi_hindi_test --limit 100
python -m benchmarks.run_benchmark benchmarks/data/mozhi_hindi_test/manifest.json --report reports/mozhi_hindi_100.json
```

Mozhi-Hindi is a generic Hindi printed-word OCR benchmark. Its word crops do
not contain the required full land-record labels and values, so its results must
not be interpreted as land-record field-extraction accuracy.

## Land-record fixture baseline

`data/land_record_test/manifest.json` is the complete currently available
labeled land-record fixture set. It contains one repository-provided fictional
demonstration image with independently encoded field ground truth and evidence
metadata. It exercises the full field-extraction benchmark but is not
representative of production land records and must not be used to claim
population accuracy.

```powershell
python -m benchmarks.run_benchmark benchmarks/data/land_record_test/manifest.json --report reports/land_record_fixture_baseline.json
```

## FUNSD English preparation

The official [FUNSD terms](https://guillaumejaume.github.io/FUNSD/work/) permit
only non-commercial research and educational use. FUNSD's official test split
contains 50 real noisy scanned forms. Its paired JSON annotations are retained
unchanged and supply the transcription from `form[*].words[*].text`; the
manifest serializes words in the provider's entity order (spaces within an
entity and newlines between entities) solely to compare a page-level
`raw_ocr_text` response. This is generic English form OCR, not land-record
field extraction.

```powershell
python -m benchmarks.prepare_funsd benchmarks/data/funsd_test
python -m benchmarks.run_benchmark benchmarks/data/funsd_test/manifest.json --report reports/funsd_test.json
```

## Dataset screening performed

- [Bangla Handwritten Dolil Dataset](https://data.mendeley.com/datasets/yk3c3xy9vm/1)
  is explicitly CC BY 4.0 and contains 653 Bangla handwritten land-record
  images, but its published description does not provide paired structured
  ground truth for this API's fields.
- [KhatianDoc](https://arxiv.org/abs/2609.03597) describes verified ground truth
  for 107 Bengali land records, but its public images redact several metadata
  fields and use a different Bengali/table schema; no verified open license was
  available in the reviewed source.

Neither is a valid source of field-level accuracy for this exact API contract.
No external dataset is bundled or benchmark result published until a dataset
has an explicit license, redistributable images, and paired ground truth for
the nine required fields.
