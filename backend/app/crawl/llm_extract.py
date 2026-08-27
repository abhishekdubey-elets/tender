"""LLM extraction for the crawl: Claude reads the fetched headlines and returns
clean leads, replacing the regex rules when an ANTHROPIC_API_KEY is configured.

One structured-output call per crawl (all headlines in a single prompt), via the
same AnthropicLLMClient the document-extraction pipeline uses. The caller
(``run_crawl``) falls back to ``extract_rule_based`` on any error, so a missing
key, quota problem or API outage can never break the crawl.
"""
from __future__ import annotations

from app.config import Settings
from app.extraction.llm import AnthropicLLMClient, LLMError

SYSTEM = """You extract sales leads for Elets Technomedia, which sells sponsorships
of Indian government-sector summits. From the numbered news headlines, keep ONLY
those where a specific, named private-sector company won Indian government business:
a contract award, order win, PLI incentive, empanelment, or similar.

Rules:
- "company" must be the actual company name exactly as written (e.g. "Tata Consultancy
  Services", "RailTel Corporation of India") — never a pronoun, clause, stock-tip label,
  or a government body.
- "government_buyer" is the government counterparty (ministry, department, PSU, state).
  If the headline names none, use "Government (India)".
- "amount" is the deal value as written (e.g. "₹500 crore"); null if not stated.
- Exclude: speculation or bidding-stage news, market roundups, opinion/analysis,
  stock recommendations, non-India deals, and defence deals.
- When unsure, leave it out. Precision over recall. An empty list is a valid answer."""

SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["leads"],
    "properties": {
        "leads": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["index", "company", "government_buyer", "amount"],
                "properties": {
                    "index": {"type": "integer", "description": "The headline's number"},
                    "company": {"type": "string"},
                    "government_buyer": {"type": "string"},
                    "amount": {"type": ["string", "null"]},
                },
            },
        }
    },
}


def _build_user_prompt(numbered: list[tuple[str, dict]]) -> str:
    lines = ["Headlines (one per line, numbered):", ""]
    for i, (vertical, item) in enumerate(numbered):
        src = item.get("source") or "Google News"
        lines.append(f"{i}. [{vertical}] ({src}) {item.get('title') or ''}")
    return "\n".join(lines)


def extract_llm(by_sector: dict[str, list[dict]], settings: Settings,
                llm: AnthropicLLMClient | None = None) -> list[dict]:
    """Extract leads from fetched headlines with Claude. Raises LLMError on failure
    (the caller falls back to the rule extractor)."""
    from app.crawl.service import _valid_company  # lazy: service imports this module

    numbered = [(vertical, item) for vertical, items in by_sector.items() for item in items]
    if not numbered:
        return []

    if llm is None:
        if not settings.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY not configured")
        import anthropic

        llm = AnthropicLLMClient(
            client=anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value()),
            model=settings.crawl_llm_model,
            effort="low",
            max_tokens=4000,
        )

    resp = llm.complete_structured(system=SYSTEM, user=_build_user_prompt(numbered), schema=SCHEMA)
    raw_leads = (resp.data or {}).get("leads") or []

    leads: list[dict] = []
    seen: set[str] = set()
    for entry in raw_leads:
        idx = entry.get("index")
        if not isinstance(idx, int) or not (0 <= idx < len(numbered)):
            continue
        vertical, item = numbered[idx]
        company = (entry.get("company") or "").strip()
        # Same shape gate as the rule extractor — the model shouldn't produce
        # junk names, but the board must never depend on that.
        if not _valid_company(company) or company.lower() in seen:
            continue
        seen.add(company.lower())
        buyer = (entry.get("government_buyer") or "").strip() or "Government (India)"
        amount = (entry.get("amount") or "").strip() or None
        title = item.get("title") or ""
        won = f"won {amount}" if amount else "won government business"
        leads.append({
            "company": company, "vertical": vertical, "government_buyer": buyer,
            "amount": amount, "what_won": title, "source": item.get("source") or "Google News",
            "date": item.get("date"), "confidence": 0.65,
            "reason_to_call": (f"{company} reportedly {won} in {vertical} government "
                               f"business — invite them to sponsor the Elets {vertical} summit "
                               f"to reach the government buyers who attend."),
        })
    return leads
