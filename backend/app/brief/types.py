"""Sales-brief inputs and outputs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.enrichment.types import EnrichmentResult
from app.opportunity.types import EpistemicTier, EventInput, Opportunity
from app.scoring.types import LeadScore


@dataclass(slots=True)
class ContactInfo:
    name: str
    title: str | None = None
    seniority: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    source_url: str | None = None
    confidence: float | None = None
    verified: bool = False


@dataclass(slots=True)
class BriefInput:
    event: EventInput
    company_name: str
    opportunity: Opportunity
    enrichment: EnrichmentResult | None = None
    score: LeadScore | None = None
    contact: ContactInfo | None = None


@dataclass(slots=True)
class Fact:
    id: str
    kind: str
    statement: str
    tier: EpistemicTier
    source_url: str | None = None
    evidence: str | None = None
    confidence: float | None = None
    value: str | None = None

    @property
    def is_verified(self) -> bool:
        return self.tier is EpistemicTier.fact


@dataclass(slots=True)
class Section:
    key: str
    title: str
    text: str
    is_inference: bool                 # False = grounded facts; True = reasoning
    relies_on: list[str] = field(default_factory=list)   # Fact ids


@dataclass(slots=True)
class BriefMeta:
    provider: str
    model: str | None
    prompt_version: str
    generated_at: datetime
    mode: str                          # "deterministic" | "llm"
    input_tokens: int | None = None
    output_tokens: int | None = None


# The ordered sections the brief must contain.
SECTION_ORDER = [
    ("trigger", "Trigger"),
    ("why_this_company", "Why this company"),
    ("why_now", "Why now"),
    ("business_need", "Business need hypothesis"),
    ("who_to_contact", "Who to contact"),
    ("reason_to_call", "Reason to call"),
    ("evidence", "Evidence"),
    ("confidence", "Confidence"),
    ("recommended_next_action", "Recommended next action"),
    ("risk", "Risk / uncertainty"),
]

# Sections whose prose an LLM may rewrite (fact-bearing ones stay deterministic).
LLM_EDITABLE = {"why_this_company", "why_now", "business_need", "reason_to_call",
                "recommended_next_action", "risk"}


@dataclass(slots=True)
class SalesBrief:
    sections: dict[str, Section]
    verified_facts: list[Fact]
    overall_confidence: float
    meta: BriefMeta
    flags: list[str] = field(default_factory=list)
    status: str = "ok"                 # "ok" | "flagged"

    def render(self) -> str:
        out = []
        for key, title in SECTION_ORDER:
            sec = self.sections.get(key)
            if not sec:
                continue
            tag = " _(inferred)_" if sec.is_inference else ""
            out.append(f"## {title}{tag}\n{sec.text}")
        if self.flags:
            out.append("## Flags\n" + "\n".join(f"- {f}" for f in self.flags))
        return "\n\n".join(out)

    def to_stored(self) -> dict:
        return {
            "status": self.status,
            "overall_confidence": self.overall_confidence,
            "flags": self.flags,
            "sections": [
                {"key": s.key, "title": s.title, "text": s.text,
                 "is_inference": s.is_inference, "relies_on": s.relies_on}
                for s in (self.sections[k] for k, _ in SECTION_ORDER if k in self.sections)
            ],
            "verified_facts": [
                {"id": f.id, "statement": f.statement, "source_url": f.source_url,
                 "evidence": f.evidence, "confidence": f.confidence}
                for f in self.verified_facts
            ],
        }
