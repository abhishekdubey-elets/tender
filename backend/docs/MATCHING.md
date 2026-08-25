# Event Deduplication & Company Resolution

Two separate matching systems that run after extraction and turn raw extracted
events into **canonical events** and **canonical companies**. Both keep the core
logic database-free (behind injected provider/store interfaces) and are tested
for false positives and false negatives.

## PART A — Event deduplication (`app/dedup/`)

The same event may appear on GeM, a ministry site, a PSU site, a company press
release and a news site. We detect that and produce **one canonical event + many
source documents** (evidence is never deleted).

Matching order (`matcher.py`):
1. **Deterministic — strong identifier**: shared normalized tender / contract /
   work-order / project / reference number → match (0.98). Authoritative even if
   other fields differ.
2. **Deterministic — composite**: same normalized government buyer **and**
   company, corroborated by value (within 2%) and/or date (within 3 days) →
   match (0.9). Buyer+company alone is *not* enough (avoids over-merging).
3. **Semantic — fallback only**: used when deterministic signals are absent.
   Embedding cosine ≥ threshold **and** a company/buyer name overlap → match
   (≤0.85). Requiring the entity overlap stops unrelated boilerplate from
   colliding. `Embedder` is injectable (`HashingEmbedder` ships as a
   dependency-free default; production should inject a real embeddings provider).

`EventDeduplicator` (`service.py`) uses a `CandidateProvider` (what already
exists) + `EventStore` (create canonical / link source). The DB store
(`canonicalization_db.py`) creates a `government_events` row or appends an
`event_sources` evidence row to the matched canonical — so all source documents
and their URLs/snippets are retained.

## PART B — Company entity resolution (`app/resolution/`)

Normalizes "M/s ABC Technologies Pvt Ltd" / "ABC Technologies Private Limited" /
"ABC Technologies Ltd." into one company **when evidence supports it**.

Normalization (`normalize.py`) strips honorifics ("M/s") and legal suffixes
("Pvt Ltd", "Private Limited", "LLP", …) to a distinctive `core`, and keeps the
punctuation-normalized full string as an alias key.

Decision (`matcher.py`) — `auto` / `suggest` / `none`:
- **registration-id conflict** (both have a CIN/GSTIN and they differ) → `none`:
  never merged, they are different companies;
- matching CIN/GSTIN/PAN → `auto` (0.95–0.99);
- matching website domain → `auto` (0.9);
- exact canonical-name (or known alias) equality → `auto` (0.85; 0.92 with a
  location match) — same name, different legal form;
- **fuzzy** name similarity only → `suggest` (never an automatic merge on
  similarity). The resolver creates a new company flagged with
  `possible_duplicate_of` for human review.

Stored per company: canonical name, aliases (every observed variation),
registration ids, website/domain, industry, location, confidence and the
resolution evidence (`companies` + `company_aliases`).

## Pipeline integration

- `app/canonicalization.py` — store-agnostic orchestration
  (`canonicalize_extracted`) + converters `ExtractedEvent → EventFingerprint /
  CompanyObservation`.
- `app/canonicalization_db.py` — DB adapters + `persist_canonical(session,
  extraction_result, raw_document)`: dedups events into `government_events` (+
  `event_sources`), resolves the awardee to a `companies` row, and sets
  `government_events.company_id` + `company_resolution_confidence`.
- Extraction gained `identifiers` (tender/contract/work-order/project/reference)
  so PART A can key on them.

## Tests

`tests/test_event_dedup.py`, `tests/test_company_resolution.py`,
`tests/test_canonicalization_integration.py` — deterministic + semantic matching,
explicit **false-positive** (different company / value gap / reg-id conflict /
similar-but-distinct name) and **false-negative** (legal-form variants, minor
value/date variation, shared identifier) cases, and end-to-end
one-canonical-event / one-company.

```bash
cd backend && ./.venv/Scripts/python -m pytest \
  tests/test_event_dedup.py tests/test_company_resolution.py \
  tests/test_canonicalization_integration.py -q
```
