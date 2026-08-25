# GovIntel — MVP Dashboard

`dashboard.html` is a self-contained MVP dashboard for the sales-intelligence
workflow. It prioritises **usability and evidence transparency over visual
complexity** and has **no CRM integration** (feedback is captured locally).

Open `dashboard.html` in a browser (no build step). It currently runs on
representative sample data that mirrors the pipeline's output shapes; wire it to
a read API over `government_events` / `companies` / `opportunities` /
`lead_scores` / `sales_briefs` / `contacts` to make it live.

## High-priority leads board
Each lead card shows company, government event, event value, government
organization, opportunity (with epistemic tier), score (ring + grade),
confidence, why-now, target contact, and reason to call. Sorted by score.

**Filters:** min score, sector, product, event type, date, government
organization, company (search), opportunity status.

## Lead detail (slide-over)
1. Event · 2. Evidence (every claim links to its source URL, tagged
FACT / INFERENCE / SPECULATION) · 3. Company profile · 4. Opportunity reasoning
(assumptions + alternatives) · 5. Score breakdown (component bars — "why 91/100")
· 6. Contact (verified person, or target roles only — never a fabricated person)
· 7. AI sales brief (inferred sections marked) + risk/uncertainty · 8. Source
documents · 9. Feedback.

**Feedback buttons:** Good lead · Bad lead · Contacted · Meeting booked ·
Not relevant · Opportunity created. Each updates the lead's status and records
the outcome (the hook for the feedback loop that tunes scoring).

## Design
Slate-tinted neutrals + indigo accent; IBM Plex Sans / Mono; theme-aware
(light/dark/system) and responsive. Evidence transparency is the visual priority:
source links everywhere, fact-vs-inference colour coding, transparent score math.
