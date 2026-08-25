"""FactBook: the set of grounded facts a brief may draw on.

Built deterministically from the inputs (event evidence, enrichment claims,
opportunity evidence, score, verified contact). Every fact keeps its source URL,
evidence snippet and confidence, so any statement citing it is traceable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.brief.types import BriefInput, Fact
from app.enrichment.types import EnrichmentField
from app.opportunity.rules import format_value
from app.opportunity.types import EpistemicTier

_COMPANY_SCALARS = [
    EnrichmentField.industry,
    EnrichmentField.hq_location,
    EnrichmentField.employee_range,
    EnrichmentField.revenue,
    EnrichmentField.business_description,
]
_COMPANY_SIGNALS = [
    EnrichmentField.recent_contracts,
    EnrichmentField.expansion_activity,
    EnrichmentField.hiring_signals,
    EnrichmentField.funding_signals,
    EnrichmentField.technology_activity,
]


@dataclass
class FactBook:
    facts: list[Fact] = field(default_factory=list)
    by_id: dict[str, Fact] = field(default_factory=dict)

    def add(self, *, kind, statement, tier, source_url=None, evidence=None, confidence=None, value=None) -> Fact:
        fid = f"F{len(self.facts) + 1}"
        fact = Fact(id=fid, kind=kind, statement=statement, tier=tier,
                    source_url=source_url, evidence=evidence, confidence=confidence, value=value)
        self.facts.append(fact)
        self.by_id[fid] = fact
        return fact

    def verified_facts(self) -> list[Fact]:
        return [f for f in self.facts if f.is_verified]

    def ids_of_kind(self, prefix: str) -> list[str]:
        return [f.id for f in self.facts if f.kind.startswith(prefix)]


def build_factbook(inp: BriefInput) -> FactBook:
    fb = FactBook()
    ev = inp.event
    ev_url = ev.evidence[0].source_url if ev.evidence else None
    ev_conf = ev.evidence[0].confidence if ev.evidence else None

    # Event evidence (verbatim, from event_sources).
    for e in ev.evidence:
        fb.add(kind="event_source", statement=e.statement, tier=EpistemicTier.fact,
               source_url=e.source_url, evidence=e.snippet, confidence=e.confidence)

    # Event scalar facts — only what is actually present (never invented).
    if ev.event_type:
        fb.add(kind="event.type", statement=f"Event type: {ev.event_type}", tier=EpistemicTier.fact,
               source_url=ev_url, confidence=ev_conf, value=ev.event_type)
    if ev.value_amount:
        fb.add(kind="event.value", statement=f"Event value: {format_value(ev.value_amount, ev.currency)}",
               tier=EpistemicTier.fact, source_url=ev_url, confidence=ev_conf, value=str(int(ev.value_amount)))
    if ev.event_date:
        fb.add(kind="event.date", statement=f"Event date: {ev.event_date.isoformat()}",
               tier=EpistemicTier.fact, source_url=ev_url, confidence=ev_conf, value=ev.event_date.isoformat())
    if ev.buyer:
        fb.add(kind="event.buyer", statement=f"Government buyer: {ev.buyer}", tier=EpistemicTier.fact,
               source_url=ev_url, confidence=ev_conf, value=ev.buyer)
    if ev.awardee:
        fb.add(kind="event.awardee", statement=f"Awardee: {ev.awardee}", tier=EpistemicTier.fact,
               source_url=ev_url, confidence=ev_conf, value=ev.awardee)
    if ev.sector:
        fb.add(kind="event.sector", statement=f"Sector: {ev.sector}", tier=EpistemicTier.fact,
               source_url=ev_url, confidence=ev_conf, value=ev.sector)

    # Company facts from enrichment (each with its claim provenance).
    if inp.enrichment is not None:
        prof = inp.enrichment.profile
        for f in _COMPANY_SCALARS:
            fr = prof.get(f)
            if fr and fr.is_known:
                claim = fr.claims[0] if fr.claims else None
                fb.add(kind=f"company.{f.value}", statement=f"{f.value}: {fr.value}",
                       tier=EpistemicTier.fact,
                       source_url=claim.source_url if claim else None,
                       evidence=claim.evidence if claim else None,
                       confidence=fr.confidence, value=str(fr.value))
        for f in _COMPANY_SIGNALS:
            fr = prof.get(f)
            if fr and fr.is_known and isinstance(fr.value, list):
                for item in fr.value[:3]:
                    fb.add(kind=f"signal.{f.value}", statement=f"{f.value}: {item.get('value')}",
                           tier=EpistemicTier.fact, source_url=item.get("source_url"),
                           evidence=item.get("evidence"), confidence=item.get("confidence"))

    # Opportunity supporting evidence (grounded) + the need (inference).
    for e in inp.opportunity.supporting_evidence:
        fb.add(kind="opportunity_evidence", statement=e.statement, tier=e.tier,
               source_url=e.source_url, evidence=e.snippet, confidence=e.confidence)
    fb.add(kind="need", statement=inp.opportunity.need_hypothesis,
           tier=inp.opportunity.epistemic_tier, evidence=inp.opportunity.reasoning,
           confidence=inp.opportunity.confidence)

    # Score (derived metric).
    if inp.score is not None:
        fb.add(kind="score", statement=f"Lead score {inp.score.total}/100 (grade {inp.score.grade})",
               tier=EpistemicTier.fact, confidence=inp.score.total / 100, value=str(inp.score.total))

    # Contact — only if verified. Unverified/None → no contact fact, so the brief
    # cannot cite a specific person.
    c = inp.contact
    if c and c.verified and c.name:
        detail = ", ".join(filter(None, [c.name, c.title]))
        fb.add(kind="contact", statement=f"Contact: {detail}", tier=EpistemicTier.fact,
               source_url=c.source_url, confidence=c.confidence, value=c.name)
        if c.email:
            fb.add(kind="contact.email", statement=f"Contact email: {c.email}", tier=EpistemicTier.fact,
                   source_url=c.source_url, value=c.email)

    return fb
