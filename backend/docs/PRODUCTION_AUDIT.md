# Production Readiness Audit

Audit of the GovIntel implementation against production concerns, with evidence,
risk, and the action taken. **Principle: don't rewrite working systems without
evidence.** Most pipeline concerns were already addressed by earlier stages
(cited below); the fixes this pass concentrate on the new API surface, secret
handling, retention and observability.

Legend — **✅ already handled** (no change) · **🔧 fixed this pass** · **📝 documented gap / deferred**.

| # | Concern | Status | Evidence / Action |
|---|---|---|---|
| 1 | **Authentication** | 🔧 | New API had none. Added API-key auth, **fail-closed** (no keys configured → all requests 401), constant-time key compare — `app/api/security.py`. |
| 2 | **Authorization** | 🔧 | Per-organization scoping on every read; feedback gated by role; cross-tenant reads return **404 not 403** (no existence leak) — `app/api/routers/leads.py`, `security.py`. |
| 3 | **API security** | 🔧 | Security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, CSP, `Cache-Control: no-store`), CORS restricted to configured origins, query/body validation via Pydantic + bounded `Query`, generic 500 handler that never leaks internals — `app/api/logging.py`, `main.py`. |
| 4 | **Secret management** | 🔧 | `SecretStr` for `anthropic_api_key` / `voyage_api_key`; DB DSN + API keys from env via `pydantic-settings`; `.env` gitignored; API key never logged (only a 6-char prefix id). ✅ pre-existing: data.gov.in API key is kept **out of the stored `source_url`** (`app/ingestion/adapters/data_gov_in.py`). |
| 5 | **Rate limiting** | 🔧 / ✅ | API: per-key+IP sliding window, 429 + `Retry-After` (`security.py`). ✅ Scrapers: per-host polite limiter already enforced (`app/ingestion/rate_limiter.py`). |
| 6 | **Scraper safety** | ✅ | robots.txt consulted (401/403 → full disallow), polite per-host rate limit + `Crawl-delay`, **no CAPTCHA/login bypass** (design boundary), identifying UA — `app/ingestion/robots.py`, `http_client.py`. No change. |
| 7 | **Retries** | ✅ | HTTP retries w/ backoff honouring `Retry-After` (`http_client.py`); extraction retries on transport/schema/grounding failure (`extraction/service.py`); enrichment/contact sources isolate failures. No change. |
| 8 | **Idempotency** | ✅ / 📝 | Ingestion dedupes by content hash + DB `uq_raw_documents(source, content_hash)`; contacts idempotent by email; dedup stage collapses duplicate events. 📝 `POST /feedback` is intentionally append-only (event log); an optional `Idempotency-Key` could de-dupe accidental double clicks — deferred. |
| 9 | **Database transactions** | 📝 | `*_db.py` writers `flush` but never `commit` — the **caller owns the unit of work** (commit/rollback per request/job). Documented in each module; the API is read-only for DB today (in-memory feedback). When wiring the DB repo, use one session per request with commit-on-success / rollback-on-error. |
| 10 | **Duplicate processing** | ✅ | Content-hash idempotency + event deduplication (`app/dedup/`) + `event_sources` keeps one canonical event with many sources. No change. |
| 11 | **Background jobs** | ✅ / 📝 | `processing_jobs` tracks type/status/attempts/error and `retryable_jobs()` is the retry queue (`app/processing/db.py`). 📝 No worker runtime (Celery/RQ) yet — deferred; the schema and job records are in place. |
| 12 | **LLM failures** | ✅ | Injectable clients; extraction retries + `failed` status on exhaustion; brief LLM output **verified and replaced** on violation (`brief/verify.py`); deterministic fallbacks. 📝 set explicit request timeouts when wiring the real Anthropic client. |
| 13 | **Malformed documents** | ✅ | Validation flags empty/oversize/unrecognised with a reason and **never discards**; extraction failures still persist the raw doc (`app/processing/`). No change. |
| 14 | **Hallucination risks** | ✅ | Extraction requires **verbatim evidence** (grounding, ungrounded snippets stripped); brief flags/removes any invented number/date/amount/contact; opportunities separate FACT/INFERENCE/SPECULATION; enrichment returns **unknown** when unverified. No change. |
| 15 | **Source provenance** | ✅ | `raw_documents.source_url` NOT NULL; `event_sources` pins URL+snippet+confidence per source; enrichment claims and brief FactBook carry source URLs; `opportunity_evidence`. No change. |
| 16 | **Logging** | 🔧 | Structured JSON request logs with request-id, method, path, status, duration — **no bodies, query strings, headers, secrets or PII** (`app/api/logging.py`). Domain layers use typed errors already. |
| 17 | **Monitoring** | 🔧 / 📝 | `/health` endpoint + request-id correlation; `processing_jobs` gives pipeline observability. 📝 metrics/alerting (Prometheus/Sentry) deferred — `sentry_dsn` hook noted. |
| 18 | **Error handling** | ✅ / 🔧 | Typed errors throughout ingestion/processing/extraction; API adds safe HTTP/exception handlers returning `{error, request_id}` with **no stack traces** to clients. |
| 19 | **Data retention** | 🔧 / 📝 | Config added: `contact_retention_days` (365) and `raw_document_retention_days` (730). 📝 the periodic purge job is a background task to implement when the worker lands. |
| 20 | **Privacy (DPDP)** | ✅ / 🔧 | Contacts carry a lawful basis, honour do-not-contact, suppress personal emails (`app/contacts/compliance.py`); PII never in URLs. 🔧 API **omits contact email/phone from list responses** (only the detail endpoint returns them); emails are never logged. |

## Fixes implemented this pass

- `app/api/` — full read API with auth, per-org authz, rate limiting, security
  headers, structured logging, safe error handling, `/health`.
- `app/config.py` — `SecretStr` secrets; API-key map; CORS origins; rate limit;
  retention-days settings.
- Tests — `tests/test_api.py` (auth/authz/validation/rate-limit/feedback) and
  `tests/test_pipeline_integration.py` (the full source→feedback chain).

## Explicitly deferred (with the hooks in place)

Background-worker runtime (Celery/RQ over the existing `processing_jobs`),
retention purge job, metrics/alerting, CRM integrations, ML retraining, and the
SQLAlchemy-backed `LeadRepository` (the in-memory one implements the same
protocol). None of these change the pipeline's correctness; they are operational
layers to add against a live database and scheduler.

## What was deliberately NOT changed

The ingestion politeness/robots/retry layer, processing validation, extraction
grounding, dedup/resolution, enrichment provenance, opportunity epistemics,
scoring determinism, contact compliance and brief verification were already
correct and covered by tests — the audit confirmed them with evidence rather than
rewriting them.
