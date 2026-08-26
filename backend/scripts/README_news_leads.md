# Google-News → government-money leads (repeatable)

Turn live Google News into ranked, deduped **"company just won government money"**
sponsorship leads for the six Elets verticals, on the dashboard.

News is a **discovery** source, not an authority: every lead is stored news-sourced
(authority `0.65`, see `app/scoring/source_authority.py`) and its score is
discounted accordingly. **Cross-check each against the official award document /
tender notice before outreach.**

## The three steps

```
1. fetch      python -m scripts.news_leads fetch --out cand.json
   (deterministic Google News RSS per vertical → candidates JSON)
                     │
                     ▼
2. extract    Workflow({ scriptPath: "scripts/gnews_leads_workflow.js",
                         args: <contents of cand.json> })
   (multi-agent: per-vertical extract → adversarial verify → synthesize;
    runs in Claude Code because the extraction needs a model. Save its
    result JSON as leads.json)
                     │
                     ▼
3. persist    python -m scripts.news_leads persist --leads leads.json
   (writes leads to Postgres as sponsorship opportunities → dashboard +
    WebSocket push; idempotent — one lead per company+product)
```

## Notes

- **Sources**: `GoogleNewsRSSAdapter` (per-query RSS). Queries per vertical live in
  `scripts/news_leads.py::QUERIES` — tune them there.
- **Why the middle step isn't pure Python**: the extraction/verification judgement
  needs an LLM. Here it uses Claude Code workflow subagents (no external key). With
  an `ANTHROPIC_API_KEY` the same prompts could run headless via
  `AnthropicLLMClient` and collapse all three steps into one command.
- **leads.json shape**: `{ "leads": [ { company, vertical, government_buyer, amount,
  what_won, reason_to_call, source, date, confidence }, ... ] }` — the workflow's
  return value.
- Leads land under the demo org (`ORG_ID`) using the per-vertical Elets summit
  products from `scripts/seed_demo_leads.py`.
