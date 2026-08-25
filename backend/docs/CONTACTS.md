# Contact Discovery

Finds business-context decision-maker contacts for a company. `app/contacts/` —
entry point `ContactDiscoveryService.discover(query) -> DiscoveryResult`.

## Compliance first (India DPDP)

- Provider **APIs only** — the adapters never scrape behind logins or solve
  CAPTCHAs (a design boundary).
- Every contact records a **lawful basis** (legitimate-interest, business
  context).
- A **do-not-contact** list (by email/name) drops matching records.
- **Personal / free-email** addresses are suppressed by default (contact kept via
  its professional profile, email removed) — `CompliancePolicy` can override.

## Flow

collect (each source) → **merge** duplicates across sources (by normalized name)
→ optional **email finder** fills/verifies missing emails → **compliance gate** →
**rank** by role fit → sorted `DiscoveryResult` (`.best()` = top contact).

- Corroboration across ≥2 independent sources marks a contact **verified** and
  raises confidence.
- Ranking rewards target-title match, seniority, a known email, verification and
  corroboration.

## Source adapters (`sources.py`, injected clients → testable offline)

- **DirectorySource** — public professional-directory people search
  (LinkedIn-style API).
- **ProviderSource** — B2B contact-data provider (Apollo/Lusha-style), often with
  emails.
- An **EmailFinderClient** (Hunter-style) can be injected to find/verify emails.

New providers implement the `ContactSource` protocol (`name`, `find(query)`).

## Pipeline bridges (`integration.py`, `db.py`)

- `contact_query_from_opportunity(...)` builds a query from the opportunity's
  `job_titles` / `departments` (the roles the KB says to target).
- `to_contact_info(candidate)` hands the top contact to the **AI sales brief**
  (so "who to contact" becomes a verified person instead of a role).
- `persist_contacts(session, company_id, result)` writes `contacts` rows
  (idempotent by email), mapping seniority/source to the schema enums.

## Tests

`tests/test_contact_discovery.py` — dedup + ranking across sources, personal-email
suppression, do-not-contact enforcement, lawful-basis recording, email finding,
failing-source isolation, and the brief bridge.

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_contact_discovery.py -q
```
