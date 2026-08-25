# Government Event Extraction Service

Turns a **normalized document** into **validated, structured government events**
using an LLM with strict schema validation.

`app/extraction/` — entry point `EventExtractionService.extract(normalized) -> ExtractionResult`.

## Design

- **Injectable LLM client** (`llm.py`): the service depends on the `LLMClient`
  protocol. Production = `AnthropicLLMClient` (Anthropic SDK, structured output
  via `output_config.format` json_schema, `claude-opus-5` default); tests =
  `FakeLLMClient` (scripted). No API key/network needed for tests.
- **Strict schema** (`schema.py`): Pydantic models with `extra="forbid"`. Every
  business field is optional and defaults to `null` — *missing → null*, never
  invented. Supported `event_type`: tender, contract_award, work_order, funding,
  policy, scheme, approval, expansion, other.
- **Evidence grounding** (`grounding.py`): each evidence `snippet` must appear
  **verbatim** (whitespace/case-normalized) in the source. Ungrounded snippets
  trigger a corrective retry, then are stripped with a warning — so paraphrased
  or invented support never passes silently.
- **Retry & validation** (`service.py`): retries on transport errors, schema
  validation failures (error fed back to the model), and ungrounded evidence,
  up to `max_attempts`. Exhaustion → `status=failed` with the reason.
- **Provenance recorded**: `ExtractionRunMeta` stores provider, exact model,
  `prompt_version`, `requested_at`/`completed_at`, attempts and token usage.
- **Determinism where possible**: current Claude models removed `temperature`, so
  exact sampling determinism isn't available. Reproducibility instead comes from
  a **versioned prompt** + **input-hash cache** (`cache` keyed by
  `model|prompt_version|sha256(text)`) — identical input reuses the prior result
  (`from_cache=True`) without another LLM call.

## Extracted fields (per event)

event_type, government_entity, entities[] (name/role/CIN/GSTIN), contract_value,
currency, sector, project, award_date, announcement_date, location, description,
evidence[] (field + verbatim snippet), confidence. One document may yield zero,
one, or many events (multiple contracts → multiple events; multiple companies →
several `entities` on one event).

## Database integration (`mapping.py`)

Each event → a `government_events` row + an `event_sources` evidence row pinned
to the originating `raw_documents` record:
- `government_events`: mapped `event_type` (raw type kept in `attributes`),
  title/summary, buyer/awardee, `value_amount` (Decimal), normalized `currency`,
  dates, `confidence`, and a stable `dedup_key` (so duplicate events collapse via
  the partial-unique index).
- `event_sources`: `source_url`, joined evidence `snippet`, the full
  `extracted_payload` (JSONB), `confidence`, `extraction_model`, `is_primary`.

`to_orm` is pure (session-less, unit-tested without a DB); `persist_events`
writes rows and sets `raw_documents.extraction_status`.

## Pipeline integration (`integration.py`)

`run_document(fetched, processor, service)` chains
FetchedDocument → SourceFile → NormalizedDocument → ExtractionResult.
`make_ingestion_document_hook(...)` returns a callback for
`IngestionRunner(on_document=...)`, so extraction runs as documents are ingested
(the runner isolates hook errors so one bad document never aborts the crawl).

## Tests

`tests/test_extraction_service.py` — the seven required scenarios (clean,
ambiguous, missing company, missing value, multiple companies, multiple
contracts, duplicate) plus retry/validation/grounding/cache/skip.
`tests/test_extraction_mapping.py` — event→ORM mapping.
`tests/test_extraction_integration.py` — bridge + ingestion hook.

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_extraction_*.py -q
```
