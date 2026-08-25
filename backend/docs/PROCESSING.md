# Document-Processing Layer

Turns a raw downloaded file into a **normalized document**.

```
source file → validate → classify → extract text → OCR (when required)
            → metadata → NormalizedDocument
```

`app/processing/` — orchestrated by `DocumentProcessor.process(source) -> ProcessingOutcome`.

## Stages

| Stage | Module | Notes |
|---|---|---|
| hashing | `hashing.py` | sha256 (canonical) + md5 + byte size — computed for **every** file, even failures |
| validation | `validation.py` | empty / oversize / unrecognized → **failure with reason**, never a silent drop |
| duplicate detection | `dedup.py`, `db.py` | exact dedupe by sha256 (in-memory `DuplicateIndex` for batches; `find_duplicate()` queries `raw_documents.content_hash`) |
| classification | `classification.py`, `sniff.py` | magic-byte sniffing (authoritative) refined by declared MIME/extension; OOXML disambiguated by zip contents |
| extraction | `extractors.py` | one extractor per class; records the **method** and a **confidence** |
| OCR | `extractors.py` (`extract_pdf`) | scanned PDF → OCR when an engine is supplied, else `needs_ocr` (retryable) |
| metadata | `metadata.py` | title/author/dates/pages/sheets, with filename/URL title fallback |

## Supported formats

HTML, PDF (text layer), **scanned PDF (OCR)**, DOCX, XLSX, JSON, plain text.
Legacy binary **DOC/XLS** are recognised but reported as `unsupported` (they need
external tooling) — recognised, not silently dropped. Extraction method ids:
`html.beautifulsoup`, `pdf.text.pypdf`, `pdf.ocr.tesseract`, `docx.python-docx`,
`xlsx.openpyxl`, `json.stdlib`, `text.decode`.

## Confidence

Deterministic extractors (HTML/JSON/DOCX/XLSX/text) report high fixed confidence
(≈0.98–1.0). PDF **text-layer** confidence is density-based (0.6–0.95). PDF **OCR**
confidence comes from the OCR engine (`OcrResult.confidence`).

## Failure handling & retryability

- Every failure path returns a `ProcessingOutcome(status=failed, error, error_kind)`
  — validation (`invalid_file`), unsupported (`unsupported`), extraction
  (`extraction_failed`). The raw bytes are preserved regardless.
- Scanned PDFs without an OCR engine return `status=needs_ocr` (not failed) so
  they can be OCR'd on a later pass.
- Each processing attempt is recorded as a **`processing_jobs`** row
  (`job_type=parse`, status, attempts, error, result). `retryable_jobs()` returns
  failed/retrying jobs that still have attempts left — the retry queue.

## Database integration (no schema change)

`db.py` maps the outcome onto the existing schema:
- `raw_documents.parsed_text` ← normalized text
- `raw_documents.parse_status` ← `parsed` / `failed` / `skipped` (needs_ocr)
- `raw_documents.mime_type`, `title`, `language` ← detected/metadata
- `raw_documents.meta` (JSONB) ← `{processing:{method,confidence,doc_class,ocr_used,error,...}, hashes:{sha256,md5}, document_metadata:{...}}`
- `processing_jobs` ← one row per attempt

`apply_outcome_fields()` is a pure function (session-less) so the mapping is unit-tested without a DB. `load_source_file()` rebuilds a `SourceFile` from a stored `raw_documents` row for reprocessing.

## OCR backend

OCR is injectable (`ExtractionContext.ocr_engine`). The default engine
(`extractors` / used only when wired up) needs `pytesseract` + `pdf2image` and the
Tesseract/Poppler binaries (`pip install -e ".[ocr]"`). Tests inject a fake
engine — no binaries required.

## Tests

`tests/test_processing_pipeline.py` (every format + OCR paths + dedup + failures)
and `tests/test_processing_db.py` (outcome→DB mapping). Fixtures:
`tests/fixtures/*` on disk plus in-memory DOCX/XLSX/PDF builders in
`tests/proc_fixtures.py`.

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_processing_*.py -q
```
