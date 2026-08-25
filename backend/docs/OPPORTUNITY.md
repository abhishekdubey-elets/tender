# Opportunity Detection Engine

Given a **government event + company profile + customer target profile + customer
products**, determines *what business needs the event could create* — as
**hypotheses, never facts**.

`app/opportunity/` — entry point `OpportunityEngine.detect(event, company, target, products, *, reasoner=None) -> OpportunityBundle`.

## Epistemic discipline (FACT / INFERENCE / SPECULATION)

`EpistemicTier` is explicit on every statement:
- **FACT** — directly stated & evidenced (the event, and grounded company
  signals from enrichment). These populate `bundle.facts`, never opportunities.
- **INFERENCE** — a logical consequence supported by a KB rule + a fact.
- **SPECULATION** — plausible but weakly supported.

Opportunities are only ever inference/speculation. A speculation **corroborated
by a real company signal is promoted to an inference** (and the signal is added
as supporting evidence). `bundle.inferences` / `bundle.speculations` partition
the output.

## Every opportunity stores

product/category, need hypothesis, trigger, reasoning, supporting evidence
(grounded), confidence, timing, assumptions, alternative explanations — plus the
relevant departments and job titles from the KB, and a scoring `factors`
breakdown.

## Configurable Product Opportunity Knowledge Base (`knowledge_base.py`)

Data, **not** an LLM prompt. Each `ProductRule` maps:
`product/category → trigger events → relevant sectors → likely business needs →
relevant departments → relevant job titles → scoring weights`.

`KnowledgeBase.from_dict(...)` loads a KB from JSON/dict; `default_knowledge_base()`
ships five categories: **cybersecurity, cloud_infrastructure, workforce_staffing,
training_skilling, events_sponsorship**. Each `BusinessNeed` carries its own
tier, timing, assumptions, alternatives and the company signals that corroborate
it.

## Deterministic first, LLM where useful

`rules.py` does all matching and scoring with no LLM:
- **match**: event type ∈ triggers, AND (keyword hit OR sector relevance), AND
  value ≥ max(rule threshold, target min-value);
- **confidence**: tier base + value magnitude + sector match + corroborating
  company signals (each weighted).

`engine.py` accepts an optional injected `OpportunityReasoner` (LLM) that may
refine the reasoning narrative and add alternatives/assumptions, with a
confidence nudge **clamped to ±0.1** — it cannot add facts or override the
grounded evidence.

## Examples encoded

- Large defence contract → *cybersecurity* (sensitive data → security need) **and**
  *workforce_staffing* (project execution → hiring).
- Digital infrastructure contract → *cloud_infrastructure* (expansion → cloud/
  compute/networking).

## Pipeline bridge (`integration.py`)

Pure converters build `EventInput` from `government_events`(+`event_sources`),
`CompanyProfileInput` from an `EnrichmentResult` (signals from the enrichment
profile), `TargetProfile` from the org's target sectors, and `ProductInput` from
the org's products. `persist_opportunities(...)` writes `opportunities` +
`opportunity_evidence` rows.

## Tests

`tests/test_opportunity_engine.py` — multiple product categories (cyber, cloud,
workforce, events, plus a custom logistics KB), FACT/INFERENCE/SPECULATION
separation, signal-driven promotion, threshold/target filtering, KB-from-dict,
and the reasoner hook.

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_opportunity_engine.py -q
```
