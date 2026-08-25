# Database Schema — Government-Event Sales Intelligence Platform

PostgreSQL 16 + `pgvector`. SQLAlchemy 2.0 ORM, Alembic migrations.

This document describes every table and how it participates in the pipeline:

```
Government Sources → Data Collection → Document Parsing → Structured Event Extraction
→ Deduplication → Event Database → Company Resolution → Company Enrichment
→ Opportunity Detection → Contact Discovery → Lead Scoring → AI Sales Brief
→ Dashboard/CRM → Feedback Loop
```

---

## Design principles (how requirements map to the schema)

| Requirement | How it is met |
|---|---|
| **Preserve source provenance** | `raw_documents` stores each fetched document verbatim; `event_sources` links every event to the exact document + URL + snippet + extraction confidence that evidenced it. |
| **Never lose the original government URL** | `raw_documents.source_url` and `event_sources.source_url` are both `NOT NULL`. The URL is snapshotted onto the evidence row so it survives even if storage is relocated. |
| **Store extraction confidence** | `confidence` columns on `government_events`, `event_sources`, `company_aliases`, `company_enrichment`, `opportunities`, `contacts`; `weight` on `opportunity_evidence`; all range-checked `0..1`. |
| **Multiple sources → one event** | `event_sources` is a many-to-one join from documents to a single `government_events` row (unique on `(government_event_id, raw_document_id)`). |
| **Multiple opportunities from one event** | `opportunities.government_event_id` is a plain FK (many opportunities per event); a unique key on `(org, event, company, product, type)` only blocks *exact* duplicates. |
| **Multiple products per organization** | `products.organization_id` one-to-many; `product_target_sectors` gives products↔sectors many-to-many. |
| **Event status: tender/award/work order/funding/policy/approval/…** | `event_type` enum (`tender, award, work_order, funding, grant, policy, approval, budget_allocation, contract, empanelment, mou, other`) + lifecycle `event_status` (`active, superseded, cancelled, duplicate`). |
| **Suitable for future CRM integration** | UUID PKs everywhere; `external_crm_id` on `opportunities`, `contacts`, `outreach`; CRM-style `outreach` activity log and pipeline `opportunity_status`. |
| **Don't store derived info as authoritative source** | Raw/authoritative layer (`raw_documents`, `event_sources`) is separate from derived/canonical layer (`government_events`, `company_enrichment`, `lead_scores`, `sales_briefs`). Derived monetary normalisation is a separate column (`value_amount_inr`) distinct from the as-reported `value_amount`. Enrichment is provider-attributed and versioned, never overwriting the core `companies` row. |
| **Indexes & unique constraints** | See each table below; partial unique indexes for nullable natural keys (CIN/GSTIN/email/dedup_key) and "one current row" patterns (enrichment, lead score). |
| **PostgreSQL** | Native enums, `JSONB`, `TIMESTAMPTZ`, `INET`, partial indexes, `pgvector` HNSW indexes, `gen_random_uuid()` server defaults. |

**Provenance chain (authoritative → derived):**

```
government_sources → raw_documents → event_sources → government_events → opportunities
                        (verbatim)     (evidence)      (canonical)        (derived)
                                                                          ↑
                                                    opportunity_evidence ─┘  (points back to event_sources / raw_documents / URL)
```

---

## Tables by pipeline stage

### Tenant configuration (who is selling, and what)
These are *inputs the customer configures*, not harvested data.

- **`organizations`** — the businesses using the platform ("my business"). Root of multi-tenancy. `slug` unique.
- **`users`** — accounts within an organization. Role enum (`admin/manager/sales_rep/analyst/viewer`). Case-insensitive unique login email (`lower(email)`). *Pipeline role:* actors in the Dashboard/CRM and Feedback Loop; opportunity owners.
- **`target_sectors`** — the org's Ideal-Customer-Profile sectors (Smart Cities, BFSI, …) with matching `keywords`/`nic_codes` in JSONB. Unique `(organization_id, name)`. *Pipeline role:* fuel for **Opportunity Detection**.
- **`products`** — what the org sells (event sponsorships, ad placements, memberships). Unique `(organization_id, name)`. *Pipeline role:* an opportunity is "event × company × **product**". 
- **`product_target_sectors`** — many-to-many products↔sectors association.

### Government Sources → Data Collection → Document Parsing
- **`government_sources`** — catalogue of portals (GeM, CPPP/eProcure, PIB, gazette, …) with `source_type`, `access_method` (`html/api/rss/playwright/manual`), `jurisdiction`, crawl cadence, and per-source scraper `config` (JSONB). *Pipeline role:* drives **Data Collection**.
- **`raw_documents`** — the **authoritative provenance layer**: one row per fetched document, with mandatory `source_url`, `content_hash` (unique per source → idempotent re-crawls), `fetched_at`, HTTP metadata, the stored bytes (inline or object-storage pointer), and the derived `parsed_text` + `parse_status`/`extraction_status`. *Pipeline role:* output of **Data Collection**, input to **Document Parsing** and **Extraction**.

### Structured Event Extraction → Deduplication → Event Database
- **`government_events`** — the **canonical, deduplicated event** (derived). Carries `event_type`, lifecycle `status`, buyer/awardee, as-reported `value_amount` + derived `value_amount_inr`, dates, `reference_number`, `dedup_key` (partial-unique), overall `confidence`, and a `pgvector` `embedding` for semantic dedup. Resolved awardee link (`company_id`, `SET NULL`) + `company_resolution_confidence`. *Pipeline role:* the **Event Database**; the spine of the system.
- **`event_sources`** — **evidence / provenance join**. One row per (event, document) with a snapshotted `source_url`, `snippet`, the per-source `extracted_payload` (JSONB), `confidence`, `extraction_model`, and `is_primary`. Unique `(government_event_id, raw_document_id)`. *Pipeline role:* implements "multiple sources → one event" and makes every event auditable back to source. `raw_document` FK is `RESTRICT` so ground truth is never cascade-deleted.

### Company Resolution → Company Enrichment
- **`companies`** — canonical resolved company entities (the government-money recipients / prospects). `normalized_name` for matching; partial-unique `cin`/`gstin`; `name_embedding` (pgvector) for fuzzy/semantic resolution; `is_verified` for human-confirmed resolution. *Pipeline role:* **Company Resolution** target.
- **`company_aliases`** — the messy strings that map onto a company (`as_reported`, `legal_name`, `abbreviation`, `misspelling`, …), with `alias_type`, `source`, `confidence`. Unique `(company_id, normalized_alias)`. *Pipeline role:* the resolver's memory — how raw awardee strings resolve.
- **`company_enrichment`** — provider-attributed, **versioned** enrichment (MCA/GSTN/web/…), raw payload in JSONB + typed fields, `confidence`, `fetched_at`, `is_current`. Partial-unique `(company_id, provider) WHERE is_current`. *Pipeline role:* **Company Enrichment**; kept separate so derived data never overwrites the core record.
- **`contacts`** — decision-makers at a company: `seniority`, title, email/phone/LinkedIn, `source`, `source_url`, `lawful_basis` (India DPDP compliance note), `do_not_contact`, `external_crm_id`. Case-insensitive partial-unique email. *Pipeline role:* **Contact Discovery**.

### Opportunity Detection
- **`opportunities`** — the core answer to *"why is this a sales opening for me, and about what?"*: ties `organization` + `government_event` + `company` (+ optional `product`/`target_sector`) with `opportunity_type`, `rationale` (derived), CRM pipeline `status`, `detected_by`, `confidence`, `owner_user_id`, `external_crm_id`. Many per event; unique only on exact `(org, event, company, product, type)`. FKs to event/company are `RESTRICT`.
- **`opportunity_evidence`** — traces each opportunity back to provenance: `evidence_type`, optional `event_source_id`/`raw_document_id`/`source_url`, `description`, `weight`. *Pipeline role:* keeps derived opportunities auditable.

### Lead Scoring → AI Sales Brief
- **`lead_scores`** — versioned scores with a transparent `factors` JSONB breakdown, `grade`, `model_version`, `is_current` (partial-unique one-current-per-opportunity). *Pipeline role:* **Lead Scoring**; history retained for tuning.
- **`sales_briefs`** — generated per-lead briefs: `content`, `format`, `status` (draft/final), `model`, `prompt_version`, token counts, optional `contact_id`/`generated_by_user_id`. *Pipeline role:* **AI Sales Brief** artefacts (schema only — no generation logic yet).

### Dashboard / CRM → Feedback Loop
- **`outreach`** — CRM activity timeline: `channel` (email/phone/linkedin/whatsapp/meeting/…), `direction`, `status`, subject/body, scheduled/occurred timestamps, `external_crm_id`. *Pipeline role:* **Dashboard/CRM** actions.
- **`sales_feedback`** — rep outcomes (`positive/converted/not_interested/bad_data/wrong_contact/…`), optional links to opportunity/outreach/lead_score, and a `data_quality_flag` that routes bad data back to extraction/resolution. *Pipeline role:* the **Feedback Loop** into scoring and data quality.

### Cross-cutting operations
- **`processing_jobs`** — every unit of pipeline work (`crawl/parse/extract/dedup/resolve/enrich/detect_opportunity/score/generate_brief/sync_crm`) with `status`, attempts/max_attempts, timing, `error`, `payload`/`result` JSONB, and loose `target_table`/`target_id` pointers. *Pipeline role:* observability + re-runnability across all stages.
- **`audit_logs`** — append-only trail (no `updated_at`): `actor_type`, `actor_user_id`, `action`, `entity_type`/`entity_id`, `before`/`after` JSONB, `ip_address`. *Pipeline role:* accountability for state changes (company merges, opportunity status changes, …).

---

## Enums (native PostgreSQL types)

`user_role, gov_source_type, access_method, jurisdiction, parse_status, extraction_status, event_type, event_status, alias_type, alias_source, enrichment_provider, opportunity_type, opportunity_status, detection_method, evidence_type, seniority, contact_source, brief_status, brief_format, outreach_channel, outreach_direction, outreach_status, feedback_outcome, job_type, job_status, actor_type, score_grade`

Each carries a trailing `other`/`unknown` safety member. Add new values with a migration (`ALTER TYPE … ADD VALUE`).

## Key indexes & constraints (highlights)

- **Idempotent crawl:** `uq_raw_documents_government_source_id_content_hash`.
- **Provenance not-null:** `raw_documents.source_url`, `event_sources.source_url`.
- **Nullable natural keys (partial-unique):** `companies.cin`, `companies.gstin`, `contacts.lower(email)`, `government_events.dedup_key`.
- **"One current" rows (partial-unique):** `company_enrichment (company_id, provider) WHERE is_current`; `lead_scores (opportunity_id) WHERE is_current`.
- **Confidence ranges:** check constraints `0 ≤ x ≤ 1` on all confidence/weight columns.
- **Vector ANN:** HNSW cosine indexes on `government_events.embedding` and `companies.name_embedding` (created in the migration, outside the ORM metadata).
- **Referential safety:** `RESTRICT` on the paths that must never cascade away provenance (`raw_documents.government_source_id`, `event_sources.raw_document_id`, `opportunities.government_event_id`/`company_id`); `SET NULL` for reversible links (`government_events.company_id`, ownership); `CASCADE` for true aggregates (evidence, aliases, enrichment, scores, briefs, outreach).

---

## Running it

```bash
# 1. Start Postgres + pgvector (creates govintel and govintel_test with extensions)
docker compose up -d db

# 2. Install deps
cd backend && python -m venv .venv && ./.venv/Scripts/pip install -e ".[dev]"

# 3. Apply the schema
alembic upgrade head

# 4. Seed reference data (government sources + demo Elets tenant)
python -m app.db.seed

# 5. Run the schema tests
pytest
```

The test-suite builds its schema by running the real Alembic migration against
`govintel_test`, so every run also verifies the migration upgrades and
downgrades cleanly. Each test executes inside a rolled-back transaction for
isolation.
