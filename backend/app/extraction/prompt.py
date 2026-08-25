"""Prompt construction. The prompt is versioned so that (prompt, model, input)
uniquely identifies an extraction — enabling caching and reproducibility.
"""
from __future__ import annotations

# Bump when the wording/rules change so cached results are not reused across
# incompatible prompt revisions.
PROMPT_VERSION = "2026-08-25.2"

SYSTEM_PROMPT = """\
You extract structured facts about government procurement and funding events from \
official Indian government documents (tenders, contract awards, work orders, \
funding releases, policies, schemes, approvals, expansions).

Strict rules:
- Extract ONLY facts explicitly stated in the document. NEVER guess or infer \
missing information.
- If a field is not stated, return null (or an empty list for list fields). Do \
not fabricate values, names, dates, or amounts.
- For every important claim (contract_value, each entity name, dates, \
government_entity) include an evidence item whose "snippet" is copied VERBATIM \
from the document — exact characters, no paraphrasing.
- A single document may describe zero, one, or several events. Emit one event \
object per distinct event (e.g. two different contracts = two events; a work \
order plus a separate funding release = two events).
- List every distinct company/organisation under "entities" with its role.
- Capture any tender/contract/work-order/project reference numbers under \
"identifiers" exactly as printed — these are used to link the same event across \
sources.
- "confidence" is your calibrated confidence (0..1) that the event and its key \
fields are correct given ONLY this document.
Return output strictly matching the provided JSON schema."""


def build_user_prompt(document_text: str, *, source_url: str | None = None, corrective: str | None = None) -> str:
    parts: list[str] = []
    if corrective:
        parts.append(f"CORRECTION FROM PREVIOUS ATTEMPT:\n{corrective}\n")
    if source_url:
        parts.append(f"Source URL: {source_url}")
    parts.append("Document text:\n\"\"\"\n" + document_text + "\n\"\"\"")
    return "\n".join(parts)
