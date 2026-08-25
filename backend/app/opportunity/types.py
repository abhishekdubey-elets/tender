"""Domain types for opportunity detection (decoupled from ORM/LLM)."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date
from typing import Any


class EpistemicTier(enum.IntEnum):
    """The epistemic status of a statement — kept explicit so hypotheses are
    never mistaken for facts."""

    speculation = 1     # plausible, weakly supported
    inference = 2       # logical consequence supported by a rule + fact
    fact = 3            # directly stated and evidenced


@dataclass(slots=True)
class Evidence:
    tier: EpistemicTier
    statement: str
    kind: str                       # "event" | "company_signal" | "rule"
    source_url: str | None = None
    snippet: str | None = None
    confidence: float | None = None


@dataclass(slots=True)
class SignalInfo:
    """A company-profile activity signal (from enrichment). Grounded fact."""

    name: str
    present: bool
    value: Any = None
    confidence: float | None = None
    source_url: str | None = None
    evidence: str | None = None


# ----- inputs ---------------------------------------------------------------
@dataclass(slots=True)
class EventInput:
    event_type: str
    value_amount: float | None = None
    currency: str | None = None
    sector: str | None = None
    buyer: str | None = None
    awardee: str | None = None
    event_date: date | None = None
    title: str | None = None
    description: str | None = None
    location: str | None = None
    evidence: list[Evidence] = field(default_factory=list)   # FACTs from event_sources

    def text(self) -> str:
        return " ".join(filter(None, [self.title, self.description, self.sector])).lower()


@dataclass(slots=True)
class CompanyProfileInput:
    name: str
    industry: str | None = None
    employee_range: str | None = None
    hq_location: str | None = None
    description: str | None = None
    signals: dict[str, SignalInfo] = field(default_factory=dict)


@dataclass(slots=True)
class TargetProfile:
    sectors: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    min_value: float | None = None
    product_categories: list[str] | None = None   # if set, restrict to these


@dataclass(slots=True)
class ProductInput:
    product_id: Any
    name: str
    category: str                    # maps to a KnowledgeBase ProductRule


# ----- outputs --------------------------------------------------------------
@dataclass(slots=True)
class Opportunity:
    product_id: Any
    product_name: str
    category: str
    need_key: str
    need_hypothesis: str
    trigger: str
    reasoning: str
    epistemic_tier: EpistemicTier    # of the NEED (inference/speculation)
    confidence: float
    timing: str
    supporting_evidence: list[Evidence] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    alternative_explanations: list[str] = field(default_factory=list)
    departments: list[str] = field(default_factory=list)
    job_titles: list[str] = field(default_factory=list)
    factors: dict = field(default_factory=dict)


@dataclass(slots=True)
class OpportunityBundle:
    facts: list[Evidence]
    opportunities: list[Opportunity]
    warnings: list[str] = field(default_factory=list)

    @property
    def inferences(self) -> list[Opportunity]:
        return [o for o in self.opportunities if o.epistemic_tier is EpistemicTier.inference]

    @property
    def speculations(self) -> list[Opportunity]:
        return [o for o in self.opportunities if o.epistemic_tier is EpistemicTier.speculation]
