"""Deterministic rule matching + scoring + opportunity construction.

This is the first-pass engine: it reads the Knowledge Base and produces grounded
opportunity hypotheses without any LLM. Confidence comes from the event value,
sector relevance and corroborating company signals; a speculation that is
corroborated by a real company signal is promoted to an inference.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.opportunity.knowledge_base import ProductRule
from app.opportunity.types import (
    CompanyProfileInput,
    EpistemicTier,
    EventInput,
    Evidence,
    Opportunity,
    ProductInput,
    TargetProfile,
)

TIER_BASE = {
    EpistemicTier.fact: 0.85,
    EpistemicTier.inference: 0.5,
    EpistemicTier.speculation: 0.3,
}


def format_value(value: float | None, currency: str | None = None) -> str:
    if not value:
        return ""
    cur = (currency or "INR").upper()
    if cur == "INR":
        if value >= 1e7:
            return f"₹{value / 1e7:.1f} cr"
        return f"₹{value:,.0f}"
    return f"{value:,.0f} {cur}"


@dataclass(slots=True)
class MatchInfo:
    matched: bool
    sector_ok: bool
    threshold: float
    keyword_ok: bool


def _sector_ok(event: EventInput, company: CompanyProfileInput, target: TargetProfile, rule: ProductRule) -> bool:
    if not rule.relevant_sectors:
        return True  # sector-agnostic rule (e.g. large-project workforce needs)
    pool = [s.lower() for s in rule.relevant_sectors]
    # Relevance is about THIS event/company's sector vs the product's sectors.
    # The customer's target-sector list is their ICP filter, not evidence that a
    # given company is in a relevant sector — including it here caused
    # out-of-sector companies (e.g. FMCG) to match products whose sectors merely
    # overlapped the customer's broad targets.
    candidates = [event.sector, company.industry]
    for c in candidates:
        if c and any(rs in c.lower() or c.lower() in rs for rs in pool):
            return True
    return False


def match_rule(event: EventInput, company: CompanyProfileInput, target: TargetProfile, rule: ProductRule) -> MatchInfo:
    type_ok = event.event_type in rule.trigger_event_types
    keyword_ok = any(kw in event.text() for kw in rule.trigger_keywords)
    sector_ok = _sector_ok(event, company, target, rule)
    threshold = max(rule.min_value or 0.0, target.min_value or 0.0)
    value_ok = threshold == 0 or (event.value_amount or 0) >= threshold
    matched = type_ok and (keyword_ok or sector_ok) and value_ok
    return MatchInfo(matched=matched, sector_ok=sector_ok, threshold=threshold, keyword_ok=keyword_ok)


def collect_facts(event: EventInput, company: CompanyProfileInput) -> list[Evidence]:
    facts = list(event.evidence)
    for name, info in company.signals.items():
        if info.present:
            facts.append(Evidence(
                EpistemicTier.fact, f"{name}: {info.value}", "company_signal",
                info.source_url, info.evidence, info.confidence,
            ))
    return facts


def build_opportunities(
    product: ProductInput,
    rule: ProductRule,
    event: EventInput,
    company: CompanyProfileInput,
    target: TargetProfile,
    match: MatchInfo,
) -> list[Opportunity]:
    value_str = f" worth {format_value(event.value_amount, event.currency)}" if event.value_amount else ""
    sector_str = f" in {event.sector}" if event.sector else ""
    counterparty = event.awardee or company.name
    trigger = f"{event.event_type.replace('_', ' ')}{value_str}{sector_str} — {counterparty}"
    event_facts = list(event.evidence)

    opportunities: list[Opportunity] = []
    for need in rule.business_needs:
        base = TIER_BASE[need.tier]
        score = base
        factors: dict = {"base": round(base, 3)}

        if event.value_amount and match.threshold:
            magnitude = min(1.0, event.value_amount / (match.threshold * 5))
            add = round(rule.weights.value * magnitude, 3)
            score += add
            factors["value"] = add

        if match.sector_ok and rule.relevant_sectors:
            add = round(rule.weights.sector, 3)
            score += add
            factors["sector"] = add

        supporting: list[Evidence] = []
        corroborating: list[str] = []
        for sig in need.supporting_signals:
            info = company.signals.get(sig)
            if info and info.present:
                add = round(rule.weights.signal * (info.confidence or 0.6), 3)
                score += add
                factors[f"signal:{sig}"] = add
                corroborating.append(sig)
                supporting.append(Evidence(
                    EpistemicTier.fact, f"{sig}: {info.value}", "company_signal",
                    info.source_url, info.evidence, info.confidence,
                ))

        # Evidence promotes a speculation to an inference.
        tier = need.tier
        if corroborating and tier is EpistemicTier.speculation:
            tier = EpistemicTier.inference

        confidence = min(0.95, round(score, 3))

        if corroborating:
            reasoning_tail = f" Corroborated by company signal(s): {', '.join(corroborating)}."
        else:
            reasoning_tail = f" No corroborating company signal yet — treat as {tier.name}."
        reasoning = (
            f"{company.name} is linked to a {event.event_type.replace('_', ' ')}{value_str}"
            f"{sector_str}. Under KB rule '{rule.name}', this could create a "
            f"{need.label.lower()} [{tier.name}]." + reasoning_tail
        )

        opportunities.append(Opportunity(
            product_id=product.product_id,
            product_name=product.name,
            category=product.category,
            need_key=need.key,
            need_hypothesis=need.label,
            trigger=trigger,
            reasoning=reasoning,
            epistemic_tier=tier,
            confidence=confidence,
            timing=need.timing,
            supporting_evidence=event_facts + supporting,
            assumptions=list(need.assumptions),
            alternative_explanations=list(need.alternatives),
            departments=list(rule.departments),
            job_titles=list(rule.job_titles),
            factors=factors,
        ))
    return opportunities
