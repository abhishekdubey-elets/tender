"""OpportunityEngine: deterministic rules first, optional LLM refinement.

The engine reads the Knowledge Base and produces grounded opportunity hypotheses
deterministically. An optional injected ``OpportunityReasoner`` may refine the
reasoning narrative and add alternative explanations/assumptions — but it cannot
add facts or move an opportunity's epistemic tier up on its own (its confidence
nudge is clamped to a small range).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.opportunity.knowledge_base import KnowledgeBase, default_knowledge_base
from app.opportunity.rules import build_opportunities, collect_facts, match_rule
from app.opportunity.types import (
    CompanyProfileInput,
    Evidence,
    EventInput,
    Opportunity,
    OpportunityBundle,
    ProductInput,
    TargetProfile,
)


@dataclass(slots=True)
class ReasonerNote:
    reasoning: str | None = None
    extra_alternatives: list[str] = field(default_factory=list)
    extra_assumptions: list[str] = field(default_factory=list)
    confidence_adjustment: float = 0.0   # clamped to [-0.1, 0.1]


@runtime_checkable
class OpportunityReasoner(Protocol):
    def refine(self, opportunity: Opportunity, facts: list[Evidence]) -> ReasonerNote: ...


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class OpportunityEngine:
    def __init__(self, knowledge_base: KnowledgeBase | None = None) -> None:
        self._kb = knowledge_base or default_knowledge_base()

    def detect(
        self,
        event: EventInput,
        company: CompanyProfileInput,
        target: TargetProfile,
        products: list[ProductInput],
        *,
        reasoner: OpportunityReasoner | None = None,
    ) -> OpportunityBundle:
        facts = collect_facts(event, company)
        opportunities: list[Opportunity] = []
        warnings: list[str] = []

        for product in products:
            if target.product_categories and product.category not in target.product_categories:
                continue
            rule = self._kb.rule_for(category=product.category, product_id=str(product.product_id))
            if rule is None:
                warnings.append(f"no KB rule for product category '{product.category}'")
                continue
            match = match_rule(event, company, target, rule)
            if not match.matched:
                continue
            opportunities.extend(build_opportunities(product, rule, event, company, target, match))

        if reasoner is not None:
            for opp in opportunities:
                note = reasoner.refine(opp, facts)
                if note.reasoning:
                    opp.reasoning = note.reasoning
                opp.alternative_explanations += [
                    a for a in note.extra_alternatives if a not in opp.alternative_explanations
                ]
                opp.assumptions += [a for a in note.extra_assumptions if a not in opp.assumptions]
                if note.confidence_adjustment:
                    opp.confidence = round(
                        _clamp(opp.confidence + _clamp(note.confidence_adjustment, -0.1, 0.1), 0.0, 0.95), 3
                    )

        opportunities.sort(key=lambda o: o.confidence, reverse=True)
        return OpportunityBundle(facts=facts, opportunities=opportunities, warnings=warnings)
