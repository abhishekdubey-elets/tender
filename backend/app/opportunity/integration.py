"""Pipeline bridge: build engine inputs from ORM/enrichment, persist results.

Kept separate so the engine core stays free of the database and enrichment
types. Input converters are pure; ``persist_opportunities`` writes
``opportunities`` + ``opportunity_evidence`` rows.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.db.enums import DetectionMethod, EvidenceType, OpportunityType
from app.db.models import GovernmentEvent, Opportunity as OpportunityRow, OpportunityEvidence
from app.enrichment.types import EnrichmentField, EnrichmentResult
from app.opportunity.types import (
    CompanyProfileInput,
    EpistemicTier,
    EventInput,
    Evidence,
    OpportunityBundle,
    ProductInput,
    SignalInfo,
    TargetProfile,
)

_SIGNAL_FIELDS = [
    EnrichmentField.recent_contracts,
    EnrichmentField.expansion_activity,
    EnrichmentField.hiring_signals,
    EnrichmentField.funding_signals,
    EnrichmentField.technology_activity,
    EnrichmentField.recent_announcements,
]

_CATEGORY_TYPE = {
    "events_sponsorship": OpportunityType.sponsorship,
    "cybersecurity": OpportunityType.other,
    "cloud_infrastructure": OpportunityType.other,
    "workforce_staffing": OpportunityType.other,
    "training_skilling": OpportunityType.other,
}

_EVIDENCE_TYPE = {
    "event": EvidenceType.event_source,
    "company_signal": EvidenceType.enrichment,
    "rule": EvidenceType.rule_match,
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def event_input_from_orm(ge: GovernmentEvent) -> EventInput:
    evidence = [
        Evidence(EpistemicTier.fact, f"{es.source_url}", "event", es.source_url, es.snippet,
                 float(es.confidence) if es.confidence is not None else None)
        for es in ge.sources
    ]
    attrs = ge.attributes or {}
    return EventInput(
        event_type=attrs.get("extraction_event_type") or ge.event_type.value,
        value_amount=float(ge.value_amount) if ge.value_amount is not None else None,
        currency=ge.currency,
        sector=attrs.get("sector") or ge.state,
        buyer=ge.buyer_name,
        awardee=ge.awardee_name,
        event_date=ge.event_date,
        title=ge.title,
        description=ge.summary,
        location=attrs.get("location"),
        evidence=evidence,
    )


def company_profile_from_enrichment(name: str, result: EnrichmentResult) -> CompanyProfileInput:
    def scalar(field: EnrichmentField) -> str | None:
        fr = result.profile.get(field)
        return fr.value if fr and fr.is_known and isinstance(fr.value, str) else None

    signals: dict[str, SignalInfo] = {}
    for field in _SIGNAL_FIELDS:
        fr = result.profile.get(field)
        if fr and fr.is_known and fr.value:
            first = fr.claims[0] if fr.claims else None
            signals[field.value] = SignalInfo(
                name=field.value, present=True,
                value=f"{len(fr.value)} item(s)" if isinstance(fr.value, list) else fr.value,
                confidence=fr.confidence,
                source_url=first.source_url if first else None,
                evidence=first.evidence if first else None,
            )
    return CompanyProfileInput(
        name=name,
        industry=scalar(EnrichmentField.industry),
        employee_range=scalar(EnrichmentField.employee_range),
        hq_location=scalar(EnrichmentField.hq_location),
        description=scalar(EnrichmentField.business_description),
        signals=signals,
    )


def target_profile_from_sectors(sectors: list[str], *, min_value: float | None = None,
                                product_categories: list[str] | None = None) -> TargetProfile:
    return TargetProfile(sectors=sectors, min_value=min_value, product_categories=product_categories)


def product_inputs_from_orm(products: list[Any]) -> list[ProductInput]:
    out = []
    for p in products:
        category = (p.attributes or {}).get("category") if getattr(p, "attributes", None) else None
        out.append(ProductInput(product_id=p.id, name=p.name, category=category or _slug(p.name)))
    return out


def persist_opportunities(
    session: Session,
    organization_id: Any,
    government_event_id: Any,
    company_id: Any,
    bundle: OpportunityBundle,
    *,
    used_reasoner: bool = False,
) -> list[OpportunityRow]:
    detected_by = DetectionMethod.hybrid if used_reasoner else DetectionMethod.rule
    rows: list[OpportunityRow] = []
    for opp in bundle.opportunities:
        row = OpportunityRow(
            organization_id=organization_id,
            government_event_id=government_event_id,
            company_id=company_id,
            product_id=opp.product_id if _is_uuid(opp.product_id) else None,
            opportunity_type=_CATEGORY_TYPE.get(opp.category, OpportunityType.other),
            title=opp.need_hypothesis,
            rationale=opp.reasoning,
            detected_by=detected_by,
            confidence=opp.confidence,
        )
        session.add(row)
        session.flush()
        for ev in opp.supporting_evidence:
            session.add(OpportunityEvidence(
                opportunity_id=row.id,
                evidence_type=_EVIDENCE_TYPE.get(ev.kind, EvidenceType.rule_match),
                source_url=ev.source_url,
                description=ev.statement,
                weight=ev.confidence,
            ))
        rows.append(row)
    session.flush()
    return rows


def _is_uuid(value: Any) -> bool:
    import uuid
    return isinstance(value, uuid.UUID)
