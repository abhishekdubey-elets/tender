"""Prompt for optional LLM prose refinement (versioned)."""
from __future__ import annotations

from app.brief.facts import FactBook
from app.brief.types import BriefInput, Section

PROMPT_VERSION = "sales-brief-v1"

SYSTEM_PROMPT = """\
You write concise, sales-ready B2B outreach briefs from a fixed set of FACTS.

Hard rules:
- Use ONLY the provided facts. NEVER invent contract values, company facts, \
contact names/emails/phones, business needs or dates.
- Do not introduce any number, amount or date that is not in the facts.
- Clearly separate verified facts from inferred reasoning; hedge inferences \
("may", "could", "likely").
- Each section must list the fact ids (F1, F2, ...) it relies on.
- Keep each section to 1-3 tight sentences. Return only the requested JSON."""


def build_user_prompt(inp: BriefInput, fb: FactBook, drafts: dict[str, Section]) -> str:
    fact_lines = [
        f"[{f.id}] ({'FACT' if f.is_verified else f.tier.name.upper()}) {f.statement}"
        + (f" — {f.source_url}" if f.source_url else "")
        for f in fb.facts
    ]
    draft_lines = [f"- {k}: {s.text}" for k, s in drafts.items()]
    return (
        "FACTS:\n" + "\n".join(fact_lines)
        + "\n\nDeterministic drafts to make more concise and sales-ready "
        "(do not add new facts):\n" + "\n".join(draft_lines)
        + "\n\nRewrite these sections only: why_this_company, why_now, business_need, "
        "reason_to_call, recommended_next_action, risk."
    )
