# AI Sales Brief Generator

Turns a government event + company profile + opportunity + score + contact +
evidence into a concise, sales-ready brief that **strictly separates verified
facts from inferred reasoning** and **never invents** contract details, company
facts, contact information, business needs or dates.

`app/brief/` — entry point `SalesBriefGenerator.generate(input, *, llm=None) -> SalesBrief`.

## Sections (all 10)

1. Trigger · 2. Why this company · 3. Why now · 4. Business need hypothesis ·
5. Who to contact · 6. Reason to call · 7. Evidence · 8. Confidence ·
9. Recommended next action · plus a **Risk / uncertainty** section explaining what
could make the lead wrong (assumptions, alternative explanations, unverified
attributes, missing contact, low-confidence evidence).

Each `Section` carries `is_inference` (grounded fact vs reasoning) and `relies_on`
(the Fact ids it cites).

## Anti-hallucination architecture

- **FactBook** (`facts.py`): every usable fact is extracted deterministically
  from the inputs — event evidence, enrichment claims, opportunity evidence,
  score, and a **verified** contact only. Each fact keeps its source URL,
  evidence snippet and confidence. If a contact is unverified/absent, no contact
  fact exists, so the brief cannot cite a person.
- **Fact-bearing sections are deterministic** (trigger, who-to-contact, evidence,
  confidence) — built only from the FactBook, so they are always traceable.
- **Optional LLM** (`llm.py`, injected) rewrites only the prose sections
  (why-this-company, why-now, business-need, reason-to-call, next-action, risk).
- **Verification** (`verify.py`): every LLM prose section is scanned for numbers,
  currency amounts, dates and contact details (emails/phones) not present in the
  FactBook. Unsupported claims trigger a retry, then are **flagged and the
  section falls back to grounded deterministic text** — the invented value never
  reaches the output (not even the flag echoes it).

## Facts vs inferences

`SalesBrief.verified_facts` are all FACT-tier with provenance; the Evidence
section lists them with `[F#]` ids and URLs. Inference sections are marked
`_(inferred)_` in the rendered output and hedge their language.

## Storage & metadata

`SalesBrief.to_stored()` gives the structured payload; `db.persist_brief(...)`
writes a `sales_briefs` row with `content` (rendered markdown), `model`,
`prompt_version`, token counts and `generated_at`. A brief that had claims
stripped is stored as `draft` (needs review); a clean brief is `final`.

## Tests

`tests/test_sales_brief.py` — deterministic grounding & completeness, no
fabrication on sparse data, verification units, **LLM-invented number flagged &
replaced**, **LLM-invented contact flagged**, clean rewrite accepted, verified
contact used without invention.

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_sales_brief.py -q
```
