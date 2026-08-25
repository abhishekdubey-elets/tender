# Read API

FastAPI app serving the dashboard. `app/api/` — build with `create_app(settings, repository)`.

## Run

```bash
cd backend && ./.venv/Scripts/python -m uvicorn "app.api:create_app" --factory --reload
```
Configure `API_KEYS` (and optionally `CORS_ORIGINS`) in `.env` first — with no
keys, every request is rejected (fail closed).

## Auth & tenancy

Send `X-API-Key: <key>` on every request. Each key maps to
`<organization_id>:<role>`. All reads are scoped to the key's organization;
another org's lead returns **404** (no cross-tenant existence leak). Feedback
requires a writing role (admin/manager/sales_rep/analyst).

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/api/leads` | high-priority leads board (org-scoped, sorted by score) |
| GET | `/api/leads/{id}` | full lead detail |
| POST | `/api/leads/{id}/feedback` | record a feedback event |

**`GET /api/leads` filters** (query params): `score_min` (0–100), `sector`,
`product`, `event_type`, `gov_org`, `status`, `company` (substring), `date_days`.

**Lead detail** includes event, evidence (each with `source_url` + FACT/INFERENCE
tier), company profile, opportunity reasoning, score components, contact
(email/phone only here — omitted from the list response), AI sales brief + risk,
and source documents.

**`POST …/feedback`** body: `{"event_type": "...", "note": "..."}` where
`event_type` is one of the ten feedback types (lead_viewed, lead_accepted,
lead_rejected, contacted, meeting_booked, opportunity_created, not_relevant,
incorrect_company, incorrect_opportunity, incorrect_contact).

## Security

API-key auth (fail closed, constant-time compare), per-org authorization,
per-key+IP rate limiting (429 + `Retry-After`), security headers + CSP, structured
request logging with a request id and **no bodies/PII/secrets**, and a generic
500 handler that never leaks internals. See `docs/PRODUCTION_AUDIT.md`.

## Data source

The app depends on a `LeadRepository` (`app/api/repository.py`). `InMemoryLeadRepository`
powers the demo/tests; a SQLAlchemy-backed implementation reads the same shape
from `government_events` / `companies` / `opportunities` / `lead_scores` /
`sales_briefs` / `contacts`.

## Tests

`tests/test_api.py` (auth, authz, validation, rate limit, feedback) and
`tests/test_pipeline_integration.py` (the full source→feedback chain through the API).
