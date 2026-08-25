# Government-Data Ingestion Framework

A modular framework for collecting documents from government sources. **Adding a
new source means writing one `SourceAdapter` subclass — nothing else in the
pipeline changes.**

## Flow

```
adapter.discover(client) → adapter.fetch(client, item) → dedupe(content hash) → parse → sink.store
        (pagination)          (rate-limit + retry + robots)   (idempotent)      (derived)   (raw + parsed)
```

The generic `IngestionRunner` (`app/ingestion/pipeline.py`) drives *any* adapter
through this flow using only the `SourceAdapter` interface.

## The `SourceAdapter` interface (`app/ingestion/base.py`)

Each adapter exposes:

| Requirement | Where |
|---|---|
| source name / type / URL | `name`, `source_type` (`GovSourceType`), `base_url` class attrs |
| discovery method | `discover(client) -> Iterator[DiscoveredItem]` |
| fetch method | `fetch(client, item) -> FetchedDocument` (default impl provided) |
| pagination | expressed inside `discover` (a generator across pages) |
| rate limiting | `rate_limit: RateLimitConfig` (enforced per-host by the client) |
| retry handling | `retry_policy` + shared `HttpClient` (backoff, honours `Retry-After`) |
| error handling | typed errors: `RobotsDisallowed`, `RateLimited`, `NotFound`, `FetchError`, `ParseError` |
| document metadata | `DocumentMetadata` (MIME, status, ETag, timestamps, source ref, …) |
| raw response storage | the sink (`InMemorySink` / `SqlAlchemySink` + `FilesystemRawStorage`) |

## Supported content types (`app/ingestion/parsers.py`)

HTML, PDF (text layer), **scanned PDF (OCR)**, Excel (`.xlsx`/`.xls`), JSON, RSS/Atom,
XML, CSV, plain text — plus **government press releases** (via RSS). Kind is
detected from an adapter hint → MIME → extension → byte sniffing. PDF text and
OCR backends are injectable (so tests need no Tesseract/Poppler binaries); OCR is
attempted only when an engine is supplied, otherwise the document is stored raw
and flagged `needs_ocr`.

## Shipped adapters (the easiest reliable sources first)

- **`PIBPressReleaseAdapter`** — Press Information Bureau press releases over
  **RSS**. RSS is the easiest reliable, ToS-friendly source: published for
  machine consumption, no auth, no CAPTCHA, one request per run.
- **`DataGovInAdapter`** — data.gov.in Open Government Data **JSON API** with
  offset/limit pagination (needs a free API key; the key is used only in the
  request URL and never persisted to `source_url`).

Generic bases `RSSAdapter` and `JSONApiAdapter` make most new feeds/APIs a small
declarative subclass.

## Adding a new source

```python
from app.ingestion.adapters.rss_adapter import RSSAdapter
from app.ingestion.registry import register_adapter
from app.db.enums import GovSourceType

@register_adapter
class MyMinistryFeed(RSSAdapter):
    name = "My Ministry Updates"
    source_type = GovSourceType.ministry
    base_url = "https://ministry.gov.in/"
    feed_url = "https://ministry.gov.in/rss"
```

Import it from `app/ingestion/adapters/__init__.py` and it self-registers. The
runner, parsers, sinks and DB layer are untouched.

## Compliance & politeness (built in, not optional)

- **robots.txt is always consulted** before fetching; disallowed URLs are
  skipped. Access-restricted robots (401/403) are treated as a full disallow.
- **Rate limiting** is per-host with a polite default (≥1 s between requests)
  and honours robots `Crawl-delay`.
- **No CAPTCHA solving, no authentication bypass.** Sources that require either
  are simply not fetched — this is a design boundary, not a TODO.
- **Not aggressive:** RSS/API adapters make one request per feed/page and carry
  content forward so `fetch` needs no extra hit.
- **Provenance preserved:** `source_url` and `fetched_at` are always recorded;
  ingestion is **idempotent** (dedupe by SHA-256 content hash), so re-runs never
  duplicate.

## Tests

`tests/test_ingestion_*.py` — all use `httpx.MockTransport` and synthetic
documents (no network, no DB, no binaries):

- `test_ingestion_http.py` — robots allow/deny, 429 retry + `Retry-After`, 500
  exhaustion, 404, rate-limiter spacing.
- `test_ingestion_parsers.py` — every content type incl. scanned-PDF OCR paths.
- `test_ingestion_adapters.py` — RSS discovery/fetch, JSON API pagination,
  registry.
- `test_ingestion_pipeline.py` — store + **idempotency**, robots-skip, and
  parse-failure-still-stores-raw.

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_ingestion_*.py -q
```
