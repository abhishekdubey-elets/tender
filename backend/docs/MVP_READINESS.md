# MVP Readiness Report — GovIntel Sales Intelligence Platform

End-to-end validation against a **controlled dataset of 12 representative Indian
government documents** (PIB press releases, CPPP/eProcurement JSON awards, news,
a scanned PDF, and edge cases). Harness: `scripts/validate_e2e.py` (re-runnable).

## ✅ Live-DB validation update — 2026-08-26

Since the first pass, **Postgres+pgvector came up and the full stack was proven
live** (this is no longer just an offline harness):

- Alembic migration `0001` applied cleanly to a live database; **the full test
  suite ran green against Postgres — 173 tests**, including the 25 DB-backed
  schema/constraint/relationship/seed tests (enums, partial indexes, check
  constraints, pgvector all verified).
- Three complete demo leads were **persisted and read back** through
  `SqlAlchemyLeadRepository` (opportunities → events → companies → enrichment →
  contacts → scores → briefs).
- The application ran **end-to-end in a browser** (FastAPI + Next.js SaaS UI):
  board, filters, detail drawer with clickable source URLs, and a **feedback
  POST that wrote an immutable `sales_feedback` row and advanced the opportunity
  status to `meeting`** in Postgres.

Net effect: the **persistence, API, dashboard and feedback** layers move from
"logic-only" to **live-proven**. What remains capped at PARTIAL is unchanged —
the stages that depend on **real external intelligence** (see below).

## ⚠️ Scope & honesty of this validation

The **offline harness** (`scripts/validate_e2e.py`) still mocks what this
environment cannot reach:

- Documents are **representative fixtures**, not live-fetched from gov portals.
- The **LLM, enrichment providers and contact providers are mocked** with
  realistic behaviour (per-company industries; contacts found for only some
  companies). This validates the pipeline's **logic, plumbing, safety controls
  and edge-case handling** — **NOT** the real-world *accuracy* of LLM extraction,
  the *quality* of live enrichment data, or contact *coverage*.
- No real LLM was run. (An OpenAI key was offered but not used — the platform is
  built on Claude/Anthropic, and that key was treated as compromised on paste.)

Verdicts below reflect this: subsystems whose correctness depends on live
external intelligence stay at **PARTIAL** until validated against real sources
with a real model. **The pipeline running cleanly is necessary, not sufficient.**

## Per-stage results (measured)

12 documents; 13 fetches (one deliberate duplicate re-fetch). 0% failure at every
stage. Latencies are in-process (mocked I/O), so treat them as lower bounds.

| Stage | Input | Output | Attempts | Failure rate | Latency (avg ms) | Confidence | Evidence retained |
|---|---|---|---|---|---|---|---|
| 1 Source ingestion | source URLs | fetched docs | 13 | 0% | 0.4 | — | source_url on every doc |
| 2 Document download | HTTP GET | raw bytes | 13 | 0% | ~0 | — | content_hash, URL |
| 3 Parsing | raw bytes | normalized text | 12 | 0% | 4.6 | — | doc_class, method |
| 4 OCR (scanned PDF) | image PDF | OCR text | 1 | 0% | — | 0.78 | ocr_used flag |
| 5 Event extraction | text | structured events | 12 | 0% | 0.1 | 0.76 | verbatim snippets + URL |
| 6 Deduplication | events | canonical events | — | 0% | 1.7 | — | one canonical + N sources |
| 7 Company resolution | awardee strings | companies | — | 0% | ~0 | — | aliases |
| 8 Company enrichment | company | profile claims | 9 | 0% | 0.3 | 0.90 | claim source URLs |
| 9 Opportunity detection | event+company+ICP | opportunities | 9 | 0% | 0.1 | — | supporting evidence |
| 10 Lead scoring | opportunity | 0–100 score | 6 | 0% | 0.1 | 0.76 | component breakdown |
| 11 Contact discovery | company+roles | contacts | 6 | 0% | ~0 | — | source, lawful basis |
| 12 Sales brief | all of the above | brief | 6 | 0% | 0.1 | — | FactBook + source URLs |
| 13 Dashboard display | leads | API JSON | 1 | 0% | 22 | — | evidence in payload |
| 14 Feedback capture | rep action | immutable event | 1 | 0% | 6 | — | append-only log |

## Difficult cases — all 11 handled ✅

| Case | Result |
|---|---|
| Duplicate documents | **PASS** — identical re-fetch skipped (content-hash idempotency); same-event-across-portals collapses to one canonical. |
| Missing company | **PASS** — event kept, `entities: []`, **no fabricated company**; correctly not turned into a sellable lead. |
| Multiple winners | **PASS** — two entities on one event (consortium). |
| Multiple contracts | **PASS** — one document → two distinct events (road + water). |
| Unclear contract value | **PASS** — `value = null` preserved, **not invented**. |
| Scanned PDF | **PASS** — no text layer detected → OCR path used → text extracted (OCR *engine* mocked). |
| Conflicting sources | **PASS** — four sources (₹50 cr vs ₹60 cr) collapse to one canonical; **each source's value retained** in evidence. |
| Outdated information | **PASS** — a 2024 award is kept but **recency-penalised** (score 76 vs 90+ for fresh). |
| Company name ambiguity | **PASS** — "Acme Defence" legal-form variants merge; **"Acme Retail" (different company) kept separate** (no false merge). |
| Irrelevant tender | **PASS** *(after a fix — see below)* — Agriculture stationery and FMCG retail produce **no lead**. |
| Hallucination control | **PASS** — an ungrounded evidence snippet ("₹999 cr secret side deal") was **stripped** at extraction. |

## 🐛 Production bug found and fixed during validation

The first honest run **FAILED `irrelevant_tender`**: an FMCG retailer (out of the
customer's ICP) produced a scored "cloud" lead. Root cause was a real defect in
`app/opportunity/rules.py::_sector_ok` — it treated the customer's *target-sector
list* as satisfying a *product's* sector relevance, so **any** company matched a
product whenever the customer's targets overlapped that product's sectors,
regardless of the company's own sector. **Fixed:** sector relevance now compares
the event/company sector to the product's sectors only. Re-validated: FMCG lead
gone, all opportunity/integration unit tests still green (no regression).

This is exactly why "the pipeline runs" was not accepted as success.

## Are the leads actually useful to a salesperson?

6 leads produced; assessed against an actionability rubric (named company + real
deal value + grounded why-now + evidence with source URLs + a contact or target
role):

- **4 USEFUL** (Metro Infratech 98, Acme Defence 92, Delta Systems 90, Zeta 76) —
  give a rep everything to act: who won what government money, why it's an
  opening, a transparent score, evidence they can click through, and a verified
  decision-maker.
- **2 PARTIAL** (Gamma Infra 51/49) — solid "who won what & why", but **no verified
  contact** (role/department only); the rep must still find the person.
- **0 junk** — the system suppressed the Agriculture and FMCG non-leads and never
  fabricated a contact, value or company.

**Honest caveat:** these usefulness numbers reflect *mocked* extraction/enrichment/
contacts. Real-world usefulness hinges on real LLM extraction accuracy and live
enrichment/contact coverage, which this run cannot measure. The **PARTIAL** rate
would very likely be higher in production (sparser enrichment, fewer contacts).

## Subsystem verdicts

| # | Subsystem | Verdict | Justification |
|---|---|---|---|
| 1 | Source ingestion | **PARTIAL** | Robots/rate-limit/retry/idempotency proven; **live gov portals (GeM/CPPP JS, CAPTCHAs, layout drift) not exercised**. |
| 2 | Document download | **PARTIAL** | HTTP fetch + provenance solid; real network variability/timeouts untested here. |
| 3 | Parsing | **PASS** | HTML/JSON/text/DOCX/XLSX real & robust; malformed docs flagged, never discarded. |
| 4 | OCR | **PARTIAL** | Scanned-PDF detection + OCR *path* works; real Tesseract accuracy on real scans unvalidated (engine mocked). |
| 5 | Event extraction | **PARTIAL** | Grounding, retry, schema-validation, hallucination-stripping all proven; **real-LLM extraction accuracy UNVALIDATED** (LLM mocked). |
| 6 | Deduplication | **PASS** | Deterministic identifier+composite; duplicate & conflicting sources handled with provenance kept. |
| 7 | Company resolution | **PASS** | Legal-form variants merge; reg-id conflict & fuzzy-only cases blocked from false merges. |
| 8 | Company enrichment | **PARTIAL** | Provenance/confidence/unknown-handling correct; **live provider data quality UNVALIDATED**, and mislabeling can mis-target (surfaced above). |
| 9 | Opportunity detection | **PASS** | Configurable KB, FACT/INFERENCE/SPECULATION separation, deterministic rules; **a real false-positive bug was found and fixed** this pass. |
| 10 | Lead scoring | **PASS** | Transparent 100-pt breakdown, deterministic, versioned, reproducible; components sum to total. |
| 11 | Contact discovery | **PARTIAL** | Dedup/rank/DPDP-compliance proven; **real provider coverage UNVALIDATED** (many real leads will have no contact). |
| 12 | Sales brief | **PASS** | FactBook grounding + invented-claim verification; deterministic brief solid (LLM prose optional/mocked). |
| 13 | Dashboard | **PASS** | API auth/scoping/filters + artifact UI; evidence surfaced with source links. |
| 14 | Feedback capture | **PASS** | Immutable append-only events, analytics, reproducible evaluation harness. |

## Overall MVP verdict: **PARTIAL — ready for a supervised pilot, not unattended production**

The platform is **architecturally complete and logically correct end-to-end**,
with strong anti-hallucination and provenance controls, and validation caught &
fixed a real targeting bug. It is **not yet production-proven** because the stages
that depend on live external intelligence (real LLM extraction accuracy,
enrichment/contact data quality) and DB execution are unvalidated here.

### To move PARTIAL → PASS
1. Run this harness against **real documents from 1–2 legally-accessible sources**
   (e.g. PIB RSS, a data.gov.in dataset) with the **real Anthropic client** — and
   score extraction accuracy on a human-labelled set. *(still open — needs a real
   Anthropic key + network)*
2. ✅ **DONE (2026-08-26)** — Postgres+pgvector stood up, `alembic upgrade head`
   applied, DB-backed tests green (173), and `SqlAlchemyLeadRepository` serving
   live data via `USE_DB_REPOSITORY=true`.
3. Wire **real enrichment + contact providers** and re-measure contact coverage
   and false-positive rate. *(still open)*
4. Add the operational layer (worker over `processing_jobs`, retention purge,
   metrics/alerting) from `docs/PRODUCTION_AUDIT.md`. *(still open)*

*Reproduce:* `cd backend && ./.venv/Scripts/python -m scripts.validate_e2e`
