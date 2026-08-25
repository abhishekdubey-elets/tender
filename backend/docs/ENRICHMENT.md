# Company Intelligence / Enrichment Service

Given a canonical company, collects and normalizes publicly available
information from prioritized sources. **Every claim keeps its source URL,
retrieval time, an evidence snippet and a confidence. Nothing is invented — a
field with no grounded claim is `unknown`.**

`app/enrichment/` — entry point `CompanyEnrichmentService.enrich(company_ref) -> EnrichmentResult`.

## Collected fields (13)

website, industry, hq_location, employee_range, revenue, subsidiaries,
business_description, recent_announcements, recent_contracts, expansion_activity,
hiring_signals, funding_signals, technology_activity.

## The `Claim` — unit of grounded truth

`field, value, source_name, source_url, tier, retrieved_at, evidence, confidence`.
Sources emit claims; the service merges them. A field's value never exists
without at least one claim behind it.

## Source adapters (`sources/`, injected clients → testable offline)

Ordered by authority (`SourceTier`): **first_party > authoritative > reputable > aggregator**.

- **WebsiteSource** (first-party) — parses the company's own site: schema.org
  Organization JSON-LD (description, address) with a meta-description fallback.
- **RegistrySource** (authoritative) — a registry client (MCA/CIN, GST, exchange
  filings) → industry, HQ, employee range, revenue, subsidiaries. Only emits
  fields the registry actually returns.
- **NewsSource** (reputable) — a news-search client; classifies each article by
  keyword into recent_contracts / expansion / hiring / funding / technology
  signals (and always a general announcement), each keeping the article URL +
  snippet as evidence.

New sources implement the `EnrichmentSource` protocol (`name`, `tier`,
`collect(ref) -> list[Claim]`).

## Merge (`merge.py`) — confidence tracking

- No claim → **unknown** (never invented).
- Scalar fields → highest-authority claim wins; agreement across sources **raises**
  confidence; disagreement **lowers** it and flags a `conflict` (with a warning).
- List fields → union of distinct items, each retaining its own provenance.

## Cache & refresh (`cache.py`, `service.py`)

- `InMemoryEnrichmentCache` with a TTL; a stale entry is treated as a miss so the
  service re-fetches. A failing source is isolated (recorded as a warning; other
  sources still contribute).
- `enrich(ref, force_refresh=False)` returns a cached result (`from_cache=True`)
  when fresh; `refresh(ref)` forces a re-fetch.

## Database integration (`db.py`)

`persist_enrichment(session, company_id, result)` writes one **current** row per
provider (derived from source tier) into `company_enrichment` (raw claims in
`data`, plus typed `industry`/`confidence`/`fetched_at`), superseding prior
current rows for that provider. Optionally fills null core `companies` fields
(website/sector/hq_state) from high-authority claims — enrichment stays separate
from, and never overwrites, verified core data.

## Tests

`tests/test_enrichment_sources.py` (each adapter, provenance retained),
`tests/test_enrichment_merge.py` (authority priority / corroboration / conflict /
unknown), `tests/test_enrichment_service.py` (profile + unknowns, source
isolation, cache hit, refresh, staleness).

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_enrichment_*.py -q
```
