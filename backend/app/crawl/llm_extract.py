"""LLM extraction for the crawl: an LLM reads the fetched headlines and returns
clean leads, replacing the regex rules when an API key is configured.

Provider order (decided in ``run_crawl``): OpenAI when OPENAI_API_KEY is set,
else Anthropic when ANTHROPIC_API_KEY is set. One structured-output call per
crawl (all headlines in a single prompt). The caller falls back down the chain
and finally to ``extract_rule_based`` on any error, so a missing key, quota
problem or API outage can never break the crawl.
"""
from __future__ import annotations

import json

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


def _numbered(by_sector: dict[str, list[dict]]) -> list[tuple[str, dict]]:
    return [(vertical, item) for vertical, items in by_sector.items() for item in items]


def extract_llm(by_sector: dict[str, list[dict]], settings: Settings,
                llm: AnthropicLLMClient | None = None) -> list[dict]:
    """Extract leads from fetched headlines with Claude. Raises LLMError on failure
    (the caller falls back down the extractor chain)."""
    numbered = _numbered(by_sector)
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
    return _leads_from_data(resp.data, numbered)


def extract_llm_openai(by_sector: dict[str, list[dict]], settings: Settings,
                       client=None) -> list[dict]:
    """Extract leads from fetched headlines with OpenAI (chat completions +
    strict JSON-schema output). Raises LLMError on failure."""
    numbered = _numbered(by_sector)
    if not numbered:
        return []

    if client is None:
        if not settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY not configured")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMError(f"openai package not installed: {exc}") from exc
        client = OpenAI(api_key=settings.openai_api_key.get_secret_value())

    try:
        resp = client.chat.completions.create(
            model=settings.crawl_openai_model,
            max_completion_tokens=4000,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": _build_user_prompt(numbered)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "government_leads", "strict": True, "schema": SCHEMA},
            },
        )
    except Exception as exc:  # includes openai API errors
        raise LLMError(str(exc)) from exc

    message = resp.choices[0].message if resp.choices else None
    content = getattr(message, "content", None) if message else None
    if not content:
        refusal = getattr(message, "refusal", None) if message else None
        raise LLMError(f"OpenAI returned no content (refusal: {refusal})")
    try:
        data = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise LLMError(f"OpenAI did not return valid JSON: {exc}") from exc
    return _leads_from_data(data, numbered)


def _leads_from_data(data: dict | None, numbered: list[tuple[str, dict]]) -> list[dict]:
    from app.crawl.service import _valid_company  # lazy: service imports this module

    raw_leads = (data or {}).get("leads") or []
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
