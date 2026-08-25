# Transparent Lead Scoring Engine

Produces a **100-point** lead score from **configurable, versioned** components,
storing the full per-component breakdown so the UI can answer *"why is this lead
91/100?"*.

`app/scoring/` — entry point `LeadScoringEngine.score(input) -> LeadScore`.

## Components (default weights, all configurable)

| Component | Max | Basis |
|---|---|---|
| Sector relevance | 25 | event/company sector ∈ target sectors |
| Event significance | 20 | contract value magnitude × event-type weight |
| Product fit | 20 | opportunity confidence (from the opportunity engine) |
| Recency | 15 | event age, full ≤30d decaying to 0 by 365d |
| Company fit | 10 | industry/size known & matching the ICP |
| Decision-maker availability | 5 | number & seniority of known contacts |
| Evidence confidence | 5 | mean confidence of supporting evidence |

Rounded components **sum exactly to the total** — the explainability invariant.

## Configuration (changeable without redeploy)

Weights are **not hardcoded**. `ScoringConfig` (version + components with
`max_points` + `params`) loads from a dict, a JSON file (`from_json`), or a DB
row. `validate()` enforces that components sum to 100. To retune scoring, edit
the JSON/DB config and reload — no code change, no redeploy. `default_config()`
ships `lead-score-v1`.

## Score versioning

Every `LeadScore` records its `config_version`, persisted to
`lead_scores.model_version`. Running two configs over the same lead yields two
comparable, versioned scores — so a new algorithm can be A/B'd against the
current one before switching. `lead_scores.is_current` marks the active score.

## Transparency

`LeadScore.to_factors()` → the JSONB stored in `lead_scores.factors`:
`{total, grade, config_version, components:[{key,label,points,max_points,explanation,detail}]}`.
`LeadScore.explain()` renders the human-readable breakdown, e.g.:

```
Lead score 91/100 (grade A, lead-score-v1):
  - Sector relevance: 22/25 — event/company sector matches a target sector
  - Event significance: 18/20 — contract_award valued at ... (value 90%, type 100%)
  - Product fit: 20/20 — opportunity confidence 0.90 (full at 0.85)
  - Recency: 14/15 — event is 40 day(s) old
  - Company fit: 9/10 — industry known, size matches ICP
  - Decision-maker availability: 4/5 — 1 contact(s); best seniority 'director'
  - Evidence confidence: 4/5 — mean supporting-evidence confidence 0.80
```

## Grades

A ≥ 80, B ≥ 65, C ≥ 45, D ≥ 25, else F.

## Pipeline bridge

`integration.scoring_input_from_opportunity(...)` builds a `ScoringInput` from an
opportunity-engine `Opportunity` + event/company/target (+ contact info).
`db.persist_lead_score(session, opportunity_id, lead_score)` writes a
`lead_scores` row (score, grade, factors, version), superseding the prior current
score.

## Tests

`tests/test_lead_scoring.py` — high / medium / low-quality leads, component-sum
invariant, factors + explain output, score versioning (two configs compared),
runtime weight changes, and invalid-config rejection.

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_lead_scoring.py -q
```
