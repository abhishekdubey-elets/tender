"""Configurable Product Opportunity Knowledge Base.

A ProductRule maps: product/category → trigger events → relevant sectors →
likely business needs → relevant departments → relevant job titles → scoring
weights. The KB is data (loadable from dict/JSON), NOT hardcoded into an LLM
prompt — the deterministic engine reads it directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.opportunity.types import EpistemicTier


@dataclass(slots=True)
class BusinessNeed:
    key: str
    label: str
    tier: EpistemicTier = EpistemicTier.inference
    timing: str = "0-6 months"
    description: str | None = None
    # Company activity signals that, if present, corroborate this need.
    supporting_signals: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScoringWeights:
    value: float = 0.15
    sector: float = 0.15
    signal: float = 0.15


@dataclass(slots=True)
class ProductRule:
    product_id: str
    name: str
    category: str
    trigger_event_types: set[str] = field(default_factory=set)
    trigger_keywords: list[str] = field(default_factory=list)
    min_value: float | None = None
    relevant_sectors: list[str] = field(default_factory=list)
    business_needs: list[BusinessNeed] = field(default_factory=list)
    departments: list[str] = field(default_factory=list)
    job_titles: list[str] = field(default_factory=list)
    weights: ScoringWeights = field(default_factory=ScoringWeights)


class KnowledgeBase:
    def __init__(self, rules: list[ProductRule]) -> None:
        self._by_category: dict[str, ProductRule] = {}
        self._by_id: dict[str, ProductRule] = {}
        for rule in rules:
            self._by_category[rule.category] = rule
            self._by_id[rule.product_id] = rule

    def rule_for(self, *, category: str | None = None, product_id: str | None = None) -> ProductRule | None:
        if product_id and product_id in self._by_id:
            return self._by_id[product_id]
        if category and category in self._by_category:
            return self._by_category[category]
        return None

    def categories(self) -> list[str]:
        return list(self._by_category)

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeBase:
        rules = []
        for r in data.get("products", []):
            needs = [
                BusinessNeed(
                    key=n["key"], label=n["label"],
                    tier=EpistemicTier[n.get("tier", "inference")],
                    timing=n.get("timing", "0-6 months"),
                    description=n.get("description"),
                    supporting_signals=n.get("supporting_signals", []),
                    assumptions=n.get("assumptions", []),
                    alternatives=n.get("alternatives", []),
                )
                for n in r.get("business_needs", [])
            ]
            w = r.get("weights", {})
            rules.append(ProductRule(
                product_id=r["product_id"], name=r["name"], category=r["category"],
                trigger_event_types=set(r.get("trigger_event_types", [])),
                trigger_keywords=r.get("trigger_keywords", []),
                min_value=r.get("min_value"),
                relevant_sectors=r.get("relevant_sectors", []),
                business_needs=needs,
                departments=r.get("departments", []),
                job_titles=r.get("job_titles", []),
                weights=ScoringWeights(
                    value=w.get("value", 0.15), sector=w.get("sector", 0.15), signal=w.get("signal", 0.15)
                ),
            ))
        return cls(rules)


def default_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase([
        ProductRule(
            product_id="cyber-1", name="Cybersecurity Services", category="cybersecurity",
            trigger_event_types={"contract_award", "work_order", "funding", "tender"},
            trigger_keywords=["defence", "defense", "data", "surveillance", "security",
                              "citizen", "health record", "identity", "payment"],
            min_value=100_000_000,
            relevant_sectors=["Defence", "BFSI", "Healthcare", "e-Governance", "Smart Cities"],
            business_needs=[BusinessNeed(
                key="security_requirements", label="Cybersecurity & data-protection need",
                tier=EpistemicTier.inference, timing="0-6 months",
                supporting_signals=["technology_activity"],
                assumptions=["assumes sensitive data is handled", "assumes compliance obligations apply"],
                alternatives=["may rely on an in-house security team", "may already be compliant/certified"],
            )],
            departments=["IT Security", "Compliance", "CISO office"],
            job_titles=["CISO", "CIO", "Head of IT Security", "IT Manager"],
        ),
        ProductRule(
            product_id="cloud-1", name="Cloud & Infrastructure", category="cloud_infrastructure",
            trigger_event_types={"contract_award", "work_order", "funding"},
            trigger_keywords=["digital", "infrastructure", "cloud", "data centre", "data center",
                              "platform", "network", "compute", "smart city", "e-governance"],
            min_value=50_000_000,
            relevant_sectors=["e-Governance", "Smart Cities", "Telecom", "IT"],
            business_needs=[BusinessNeed(
                key="infrastructure_expansion", label="Cloud/compute/networking scale-up",
                tier=EpistemicTier.inference, timing="0-9 months",
                supporting_signals=["expansion_activity", "technology_activity"],
                assumptions=["assumes new digital workloads", "assumes cloud adoption"],
                alternatives=["may use existing capacity", "may choose on-prem"],
            )],
            departments=["IT Infrastructure", "Cloud/DevOps"],
            job_titles=["CTO", "Head of Infrastructure", "Cloud Architect"],
        ),
        ProductRule(
            product_id="staff-1", name="Workforce & Staffing", category="workforce_staffing",
            trigger_event_types={"contract_award", "work_order"},
            trigger_keywords=["project", "execution", "construction", "deploy", "rollout", "implementation"],
            min_value=100_000_000,
            relevant_sectors=[],   # broad — large execution projects across sectors
            business_needs=[BusinessNeed(
                key="workforce_requirement", label="Hiring / workforce ramp-up for project execution",
                tier=EpistemicTier.inference, timing="0-6 months",
                supporting_signals=["hiring_signals", "expansion_activity"],
                assumptions=["assumes in-house execution", "assumes net-new headcount"],
                alternatives=["may subcontract execution", "may redeploy existing staff"],
            )],
            departments=["HR", "Talent Acquisition", "Operations"],
            job_titles=["CHRO", "Head of Talent", "HR Manager", "Project Director"],
        ),
        ProductRule(
            product_id="skill-1", name="Training & Skilling", category="training_skilling",
            trigger_event_types={"funding", "scheme", "policy", "contract_award"},
            trigger_keywords=["skill", "training", "capacity building", "education", "workforce development"],
            relevant_sectors=["Education & EdTech", "e-Governance"],
            business_needs=[BusinessNeed(
                key="skilling_need", label="Workforce training / capacity building",
                tier=EpistemicTier.speculation, timing="3-12 months",
                supporting_signals=["hiring_signals"],
                assumptions=["assumes skill gaps in new mandate"],
                alternatives=["may have internal L&D", "may not prioritise training"],
            )],
            departments=["L&D", "HR"],
            job_titles=["Head of L&D", "CHRO"],
        ),
        ProductRule(
            product_id="event-1", name="Event Sponsorship & Media", category="events_sponsorship",
            trigger_event_types={"contract_award", "funding", "expansion", "work_order"},
            trigger_keywords=["smart city", "digital", "governance", "summit", "launch", "mission"],
            relevant_sectors=["Smart Cities", "e-Governance", "BFSI", "Healthcare", "Education & EdTech"],
            business_needs=[BusinessNeed(
                key="visibility_thought_leadership",
                label="Brand visibility / thought-leadership at sector events",
                tier=EpistemicTier.speculation, timing="1-6 months",
                supporting_signals=["funding_signals", "expansion_activity", "recent_contracts"],
                assumptions=["assumes a marketing budget", "assumes interest in sector visibility"],
                alternatives=["may focus purely on delivery", "may already sponsor rival events"],
            )],
            departments=["Marketing", "Corporate Communications", "Business Development"],
            job_titles=["CMO", "Head of Marketing", "BD Head"],
        ),
    ])
