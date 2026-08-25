# Architecture Audit & Implementation Plan
**Project:** Government-Money → Sales-Opportunity Intelligence System
**Date:** 2026-08-25
**Status of repo at audit time:** EMPTY — greenfield build (no code, no git history, no config)

> **Core question the system must answer:**
> *"Which companies just received government money/contracts, why does that create an opportunity for my business, and who should I call?"*

---

## 0. Executive summary

The working directory `anurag-sir/` was empty at audit time. There is **no existing code to reverse-engineer**, so every "existing component" question resolves to *not implemented*. This document is therefore a **from-scratch architecture + phased plan** for the target pipeline:

```
Government Sources → Data Collection → Document Parsing → Structured Event Extraction
→ Deduplication → Event Database → Company Resolution → Company Enrichment
→ Opportunity Detection → Contact Discovery → Lead Scoring → AI Sales Brief
→ Dashboard/CRM → Feedback Loop
```

This is a **data-ingestion + entity-resolution + LLM-enrichment + CRM** platform. The hard parts are NOT the LLM calls — they are (1) robust, self-healing scrapers against government portals, (2) entity resolution (messy Indian company-name strings → canonical companies), and (3) deduplication of the same award reported by multiple sources. Plan accordingly.

---

## A. Current architecture

**None.** Empty repository. No backend, frontend, database, jobs, or config exist.

The remainder of this document is the *proposed* architecture, presented as the target to build toward.

### Proposed high-level architecture

- **Ingestion workers** (scheduled, per-source) pull from government portals → store raw documents.
- **Parsing workers** normalize PDFs/HTML/RSS into clean text.
- **Extraction workers** call Claude to turn text into structured award/contract *events* (validated against Pydantic schemas).
- **Dedup + resolution** collapse duplicate events and map awardee strings to canonical company records (fuzzy + vector similarity).
- **Enrichment** augments companies (registry data, sector, size) and detects *opportunities* (rules + LLM: "why is this a sales opening").
- **Contact discovery** finds decision-makers; **lead scoring** ranks them.
- **Brief generation** (Claude) writes a per-lead sales brief.
- **API + Dashboard/CRM** expose the pipeline; a **feedback loop** captures rep outcomes to tune scoring.

All stages are decoupled through the database and a task queue so any stage can be re-run/back-filled independently.

---

## B. Existing components

| # | Component | Status |
|---|-----------|--------|
| 1 | Backend framework/language | ❌ None |
| 2 | Frontend framework | ❌ None |
| 3 | Database & ORM | ❌ None |
| 4 | Authentication | ❌ None |
| 5 | API structure | ❌ None |
| 6 | Background workers/jobs | ❌ None |
| 7 | Scraping/crawling code | ❌ None |
| 8 | AI/LLM integrations | ❌ None |
| 9 | Dashboard/UI | ❌ None |
| 10 | Deployment config | ❌ None |
| 11 | Env vars / secrets | ❌ None defined |
| 12 | Tests | ❌ None |
| 13 | Integrations | ❌ None |
| 14 | **Already implemented** | ❌ Nothing |
| 15 | **Partially implemented** | ❌ Nothing |
| 16 | **Completely missing** | ⚠️ Everything (see Section C) |

> Note: `finintel-ui.html` exists on the Desktop (one level up, outside this repo). It was NOT reviewed and is not part of this project unless you say so. If it's a dashboard mockup, it could seed Phase 7's UI.

---

## C. Missing components (i.e. everything)

Mapped to the target pipeline:

1. **Government Sources registry** — a catalog of source portals, their access method, and cadence.
2. **Data Collection** — per-source scrapers/API clients (GeM, CPPP/eProcurement, PIB, ministry sites, state portals), with rate-limiting, retries, and change detection.
3. **Document Parsing** — PDF/HTML/RSS → clean text; OCR for scanned tenders.
4. **Structured Event Extraction** — LLM → typed award/contract events.
5. **Deduplication** — collapse the same award across sources/reruns.
6. **Event Database** — canonical store of extracted events + provenance.
7. **Company Resolution** — awardee string → canonical company entity.
8. **Company Enrichment** — registry (CIN/GSTIN), sector, size, location.
9. **Opportunity Detection** — rules + LLM to explain *why it's a sales opening for you*.
10. **Contact Discovery** — decision-makers (LinkedIn/Apollo/Lusha/etc.).
11. **Lead Scoring** — rank opportunities/contacts.
12. **AI Sales Brief** — Claude-generated per-lead brief.
13. **Dashboard/CRM** — review, assign, act, track.
14. **Feedback Loop** — capture rep outcomes → tune scoring & extraction.
15. **Cross-cutting:** auth, API, task queue, config/secrets, migrations, observability, tests, CI/CD, deployment.

---

## D. Technical risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Scraper fragility** — govt portals change layout / add JS / rate-limit | 🔴 High | Isolate each source behind an adapter interface; snapshot raw HTML; alert on schema drift; use Playwright only where needed; **never bypass CAPTCHAs** (policy + legal) — flag those sources for manual/API access. |
| **Entity resolution ambiguity** — "M/s ABC Pvt Ltd" vs "ABC Private Limited" vs "ABC Ltd." | 🔴 High | Normalization pipeline + `rapidfuzz` + vector similarity; a human-review queue for low-confidence merges; keep an `company_aliases` table; never hard-merge on weak signals. |
| **Deduplication false-merge / false-split** | 🟠 Med | Composite keys (awardee + tender ID + value + date window) + embedding similarity threshold; store all source rows, merge at a view layer so merges are reversible. |
| **LLM extraction hallucination / cost drift** | 🟠 Med | Structured outputs (`output_config.format`) with strict schemas + `messages.parse()`; cite source text; validate numeric fields; batch low-priority extraction via the Batch API (50% cost); use `claude-sonnet-5`/`claude-haiku-4-5` for high-volume extraction, reserve `claude-opus-5` for briefs. |
| **Contact/PII compliance (India DPDP Act 2023)** | 🔴 High | Only collect business-context professional contacts from lawful sources; honor takedown; do not scrape behind logins in violation of ToS; document lawful basis; keep PII out of URLs/logs. |
| **Scraping legality / ToS** | 🟠 Med | Prefer official APIs/open-data where they exist; respect robots.txt & rate limits; keep an auditable per-source access-method record. |
| **OCR quality on scanned tenders** | 🟠 Med | Tesseract + confidence thresholds; route low-confidence docs to a review queue; keep original for re-processing. |
| **Source schema drift silently corrupting data** | 🟠 Med | Validate every parsed record; monitor extraction success rate per source; version raw snapshots. |
| **Single-tenant secrets sprawl** | 🟡 Low | Central `pydantic-settings` config + `.env` (dev) / secret manager (prod); never commit secrets. |
| **Over-building before value** | 🟠 Med | Build a thin vertical slice (ONE source, end-to-end to a brief) before broadening — see Section J. |

---

## E. Recommended implementation order

Guiding principle: **one thin vertical slice through the entire pipeline first**, then broaden sources and deepen each stage.

1. **Foundations** — repo, Docker, Postgres+pgvector, FastAPI skeleton, config, migrations, CI.
2. **Thin slice ingestion** — ONE government source → raw store → parse → clean text.
3. **Structured extraction + Event DB + dedup** for that source.
4. **Company resolution + enrichment.**
5. **Opportunity detection + lead scoring** (rules first).
6. **Contact discovery.**
7. **AI sales brief.**
8. **Dashboard/CRM** (make the slice usable by a human).
9. **Feedback loop.**
10. **Broaden** — add sources, add orchestration/monitoring, harden.

Value checkpoint: after step 8 you can already answer the core question for one source. Everything after is coverage and quality.

---

## F. Files that should be modified

**None.** The repository is empty — there is nothing to modify. (Left in intentionally to answer the brief: no pre-existing files exist.)

---

## G. Files that should be created

Proposed layout (Python backend + Next.js frontend; monorepo):

```
anurag-sir/
├─ README.md
├─ docker-compose.yml                # postgres(+pgvector), redis, api, worker, frontend
├─ .env.example                      # documented env vars (see Section K)
├─ .gitignore
├─ pyproject.toml                    # backend deps + ruff/mypy/pytest config
│
├─ backend/
│  ├─ app/
│  │  ├─ main.py                      # FastAPI entrypoint
│  │  ├─ config.py                    # pydantic-settings
│  │  ├─ db/
│  │  │  ├─ session.py                # SQLAlchemy engine/session
│  │  │  ├─ base.py
│  │  │  └─ models/                   # sources, raw_documents, events, companies,
│  │  │     └─ ...                    #   company_aliases, contacts, opportunities,
│  │  │                               #   lead_scores, sales_briefs, feedback, users
│  │  ├─ schemas/                     # Pydantic API + LLM-extraction schemas
│  │  ├─ api/
│  │  │  ├─ deps.py                   # auth deps
│  │  │  └─ routers/                  # events, companies, opportunities, leads,
│  │  │                               #   briefs, sources, feedback, auth
│  │  ├─ ingestion/
│  │  │  ├─ base.py                   # SourceAdapter interface
│  │  │  └─ sources/                  # one module per govt source (gem, cppp, pib, ...)
│  │  ├─ parsing/                     # pdf.py, html.py, ocr.py, rss.py
│  │  ├─ extraction/                  # llm_extract.py (Claude structured output)
│  │  ├─ dedup/                       # normalize.py, matcher.py (fuzzy + vector)
│  │  ├─ resolution/                  # company_resolver.py
│  │  ├─ enrichment/                  # registry.py, company_enrich.py
│  │  ├─ opportunity/                 # detect.py (rules + LLM)
│  │  ├─ contacts/                    # discovery.py
│  │  ├─ scoring/                     # lead_score.py
│  │  ├─ briefs/                      # generate_brief.py (Claude)
│  │  ├─ workers/                     # celery_app.py, tasks per stage, beat schedule
│  │  └─ llm/                         # anthropic client wrapper, prompt templates
│  ├─ alembic/                        # migrations
│  └─ tests/                          # unit + integration + scraper fixtures
│
├─ frontend/                          # Next.js + TS + Tailwind + shadcn/ui
│  ├─ app/                            # dashboard, opportunities, company, lead, brief, feedback
│  ├─ components/
│  └─ lib/api.ts
│
└─ .github/workflows/ci.yml           # lint, type-check, test
```

---

## H. Dependencies to install

### Backend (Python 3.12+)
- **Web/API:** `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`
- **DB/ORM:** `sqlalchemy>=2`, `alembic`, `psycopg[binary]`, `pgvector`
- **Jobs/queue:** `celery`, `redis` (broker + result backend); `celery[redis]`
- **Scraping:** `httpx`, `beautifulsoup4`, `lxml`, `playwright`, `feedparser`, `tenacity` (retries)
- **Parsing/OCR:** `pdfplumber`, `pymupdf`, `pytesseract`, `pillow` (+ system Tesseract binary)
- **Matching:** `rapidfuzz`
- **Embeddings (for dedup/resolution):** `voyageai` (Voyage AI) **or** `sentence-transformers` (local, e.g. BGE) — **note: Anthropic has no embeddings endpoint**, so a separate embeddings provider is required.
- **LLM:** `anthropic`
- **Observability/quality:** `structlog`, `sentry-sdk` (optional)
- **Dev:** `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `respx`/`vcrpy` (record scraper responses)

### Frontend (Node 20+)
- `next`, `react`, `react-dom`, `typescript`, `tailwindcss`, `@tanstack/react-query`, `recharts` (or `visx`), `shadcn/ui`, `zod`

### Infra
- Docker + docker-compose; Postgres 16 with the `pgvector` extension; Redis 7.

### LLM model choices (from current Claude API reference, 2026-08-25)
- **High-volume extraction / opportunity classification:** `claude-sonnet-5` (or `claude-haiku-4-5` for the cheapest bulk passes). Use the **Batch API** for non-urgent back-fills (50% cost).
- **Sales briefs (quality-sensitive, low volume):** `claude-opus-5`.
- Use **structured outputs** (`output_config: {format: {...}}` + `messages.parse()`) for extraction, not free-text parsing. Use adaptive thinking (`thinking: {type: "adaptive"}`) for the brief step.

---

## I. Database changes required

Greenfield → this is the **initial schema** (create via Alembic migration 0001). Core tables:

- **`sources`** — id, name, base_url, access_method (`api`/`html`/`playwright`/`rss`), cadence, enabled, last_run_at.
- **`raw_documents`** — id, source_id, url, fetched_at, content_hash, raw_blob/path, mime_type, http_status. *(idempotency via content_hash + url)*
- **`events`** — id, raw_document_id (provenance), event_type (`contract_award`/`grant`/`budget_allocation`/`tender_result`), awardee_raw_name, buyer/ministry, value_amount, currency, award_date, description, source_confidence, extraction_model, dedup_key, `embedding vector`. 
- **`companies`** — id, canonical_name, cin, gstin, sector, size_band, hq_state, website, `name_embedding vector`.
- **`company_aliases`** — id, company_id, alias_text, source, confidence. *(entity resolution)*
- **`contacts`** — id, company_id, name, title, seniority, email (nullable), phone (nullable), linkedin_url, source, consent/lawful_basis note.
- **`opportunities`** — id, event_id, company_id, opportunity_type, rationale (why it's a fit), status, created_at.
- **`lead_scores`** — id, opportunity_id, score, factors (jsonb), model_version, scored_at.
- **`sales_briefs`** — id, opportunity_id, contact_id, brief_text, model, tokens, generated_at.
- **`feedback`** — id, opportunity_id/lead, rep_id, outcome (`contacted`/`meeting`/`won`/`lost`/`bad_data`), notes, created_at. *(feeds scoring)*
- **`users`** — id, email, role, hashed_password/SSO ref.

**Extensions:** `CREATE EXTENSION vector;` (pgvector) for `events.embedding`, `companies.name_embedding` (dedup + resolution via cosine similarity).

**Indexing:** btree on `raw_documents.content_hash`, `events.dedup_key`, `companies.cin`/`gstin`; ivfflat/hnsw on the vector columns.

---

## J. Phased implementation plan

Each phase ends in something runnable and testable. **Do not start Phase 1 until this audit is approved.**

### Phase 0 — Foundations (infra & skeleton)
- Init git, monorepo layout (Section G), `docker-compose` (Postgres+pgvector, Redis), `.env.example`, `pyproject.toml`, CI (ruff/mypy/pytest).
- FastAPI health endpoint; SQLAlchemy + Alembic wired; Celery + Redis "hello task".
- **Exit:** `docker compose up` runs API + worker + DB; migration 0001 applies.

### Phase 1 — Thin-slice ingestion + parsing (ONE source)
- Pick ONE high-value, legally-clean source (recommend an official API/open-data or RSS source first, e.g. PIB press releases or an eProcurement results feed).
- Implement `SourceAdapter` + that source; store `raw_documents` idempotently; parse to clean text (PDF/HTML/RSS).
- **Exit:** scheduled job pulls new docs and stores clean text; scraper responses recorded as test fixtures.

### Phase 2 — Structured extraction + Event DB + dedup
- Claude structured-output extraction → validated `events`; compute embeddings; dedup by composite key + vector similarity.
- **Exit:** raw docs become deduped, typed events with provenance; extraction success rate tracked per source.

### Phase 3 — Company resolution + enrichment
- Normalize awardee strings → resolve to `companies` (fuzzy + vector); `company_aliases`; low-confidence review queue.
- Enrich (CIN/GSTIN/sector/size) from registry/open data.
- **Exit:** events link to canonical companies; a human can approve/reject uncertain merges.

### Phase 4 — Opportunity detection + lead scoring
- Rules first (sector + award value + recency + fit-to-your-offering) → `opportunities` with a plain-language rationale; optional LLM rationale.
- Rule-based `lead_scores` with transparent factors (jsonb).
- **Exit:** ranked opportunities answering "why is this a fit."

### Phase 5 — Contact discovery
- Pluggable providers (LinkedIn/Apollo/Lusha/Hunter). Compliance gate (DPDP) before storing PII.
- **Exit:** opportunities carry candidate decision-maker contacts with source + lawful-basis note.

### Phase 6 — AI sales brief
- `claude-opus-5` generates a per-lead brief (who/why/what to say/what they just won), grounded in the event + company + contact.
- **Exit:** one-click brief per lead.

### Phase 7 — Dashboard / CRM
- Next.js UI: opportunity feed, company & event detail, lead list, brief view, assign/status, review queues.
- Auth (email/password or SSO) + role-based access.
- **Exit:** a rep can log in, browse ranked opportunities, read a brief, and act — the core question is answerable end-to-end for one source.

### Phase 8 — Feedback loop
- Capture rep outcomes (`feedback`) → surface in scoring factors; flag `bad_data` back to extraction/resolution.
- **Exit:** outcomes measurably influence ranking and data-quality queues.

### Phase 9 — Broaden & harden
- Add remaining government sources behind the adapter interface; add orchestration/monitoring (per-source success dashboards, alerting on drift), Batch-API back-fills, backups, and deployment hardening.
- **Exit:** multi-source coverage with observability.

---

## K. Environment variables & secrets expected (proposed `.env.example`)

```
# Database
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/govintel
# Redis / Celery
REDIS_URL=redis://localhost:6379/0
# Anthropic
ANTHROPIC_API_KEY=            # or use `ant auth login` profile
LLM_EXTRACTION_MODEL=claude-sonnet-5
LLM_BRIEF_MODEL=claude-opus-5
# Embeddings provider (pick one)
VOYAGE_API_KEY=               # if using Voyage AI
# Contact-discovery providers (Phase 5)
APOLLO_API_KEY=
HUNTER_API_KEY=
# Auth
JWT_SECRET=
# Scraping
SCRAPER_USER_AGENT=
REQUEST_RATE_LIMIT_PER_MIN=
# Observability (optional)
SENTRY_DSN=
```

---

## Open questions for the product owner (resolve before Phase 1)

1. **Which government sources** are in scope for v1, and in what priority? (GeM, CPPP/eProcurement, PIB, specific ministries, state portals?)
2. **What is "your business's" offering?** Opportunity detection needs your ICP/fit rules (e.g., "companies that won smart-city contracts → target for our Smart City events/sponsorships").
3. **Geography/sector focus** (national vs specific states/sectors)?
4. **Contact-discovery providers** available (existing LinkedIn/Apollo/Lusha subscriptions)? DPDP compliance owner?
5. **Team size / deployment target** (single-tenant internal tool vs multi-user SaaS; on-prem vs cloud)?
6. Is `finintel-ui.html` intended as the dashboard starting point?
```
