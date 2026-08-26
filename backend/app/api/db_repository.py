"""SQLAlchemy-backed LeadRepository.

Reads the dashboard's lead shape from the persisted tables — anchored on an
``opportunities`` row — joining ``government_events`` (+ ``event_sources``),
``companies`` (+ current ``company_enrichment`` and ``contacts``), the current
``lead_scores`` row and the latest ``sales_briefs`` row. Writes feedback to
``sales_feedback`` (append-only) and advances the opportunity status.

Fidelity notes (the schema stores facts; a little presentation is reconstructed):
- ``score_components`` come straight from ``lead_scores.factors`` (stored).
- The structured brief is parsed back from ``sales_briefs.content`` (the render
  format is self-authored, so the parse is exact — not fragile NLP).
- The opportunity's assumptions / alternatives / timing / job-titles / epistemic
  tier are not first-class columns; they are reconstructed from the Product
  Opportunity Knowledge Base by the opportunity's product category. If the
  product isn't linked (KB-only id), these degrade to sensible defaults.

The builder functions are pure (operate on already-loaded ORM objects), so the
mapping is unit-testable without a database.
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import OpportunityStatus, OpportunityType
from app.db.models import (
    Company,
    Contact,
    GovernmentEvent,
    LeadScore,
    Opportunity,
    SalesBrief,
)
from app.feedback.db import record_feedback as _record_feedback_row
from app.feedback.types import FeedbackEventType
from app.opportunity.knowledge_base import KnowledgeBase, default_knowledge_base

_EVENT_LABELS = {
    "tender": "Tender", "award": "Contract award", "work_order": "Work order",
    "funding": "Funding", "grant": "Grant", "policy": "Policy", "approval": "Approval",
    "budget_allocation": "Budget allocation", "contract": "Contract",
    "empanelment": "Empanelment", "mou": "MoU", "other": "Event",
}

_FEEDBACK_STATUS = {
    FeedbackEventType.lead_accepted: OpportunityStatus.qualified,
    FeedbackEventType.opportunity_created: OpportunityStatus.qualified,
    FeedbackEventType.contacted: OpportunityStatus.contacted,
    FeedbackEventType.meeting_booked: OpportunityStatus.meeting,
    FeedbackEventType.lead_rejected: OpportunityStatus.disqualified,
    FeedbackEventType.not_relevant: OpportunityStatus.disqualified,
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")


# --------------------------------------------------------------------------- #
# Pure builders (no session access)
# --------------------------------------------------------------------------- #
def _kb_rule(opp: Opportunity, kb: KnowledgeBase):
    category = None
    product = opp.product
    if product is not None:
        attrs = getattr(product, "attributes", None) or {}
        category = attrs.get("category") or _slug(product.name)
    return kb.rule_for(category=category, product_id=str(opp.product_id) if opp.product_id else None)


def _current_score(opp: Opportunity) -> LeadScore | None:
    scored = [ls for ls in opp.lead_scores]
    current = [ls for ls in scored if ls.is_current]
    if current:
        return current[0]
    return max(scored, key=lambda ls: ls.scored_at) if scored else None


def _event_dict(ge: GovernmentEvent) -> dict:
    attrs = ge.attributes or {}
    return {
        "type": attrs.get("extraction_event_type") or ge.event_type.value,
        "type_label": _EVENT_LABELS.get(ge.event_type.value, "Event"),
        "title": ge.title,
        "value": float(ge.value_amount) if ge.value_amount is not None else None,
        "org": ge.buyer_name, "department": ge.buyer_department,
        "sector": attrs.get("sector") or ge.state,
        "date": ge.event_date.isoformat() if ge.event_date else None,
        "reference": ge.reference_number,
        "location": attrs.get("location") or ge.state,
    }


def _best_contact(company: Company) -> Contact | None:
    contacts = list(company.contacts) if company.contacts else []
    contacts = [c for c in contacts if not c.do_not_contact]
    if not contacts:
        return None
    return sorted(contacts, key=lambda c: (c.is_verified, float(c.confidence or 0)), reverse=True)[0]


def _company_profile(company: Company) -> dict:
    enr = next((e for e in company.enrichments if e.is_current), None) if company.enrichments else None
    description = None
    if enr and enr.data:
        for claim in enr.data.get("claims", []):
            if claim.get("field") == "business_description":
                description = claim.get("value")
    return {
        "industry": company.sector or (enr.industry if enr else None),
        "hq": ", ".join(filter(None, [company.hq_city, company.hq_state])) or None,
        "size": company.size_band or (str(int(enr.employee_count)) if enr and enr.employee_count else None),
        "revenue": float(enr.annual_revenue) if enr and enr.annual_revenue else None,
        "website": company.website, "description": description,
    }


def _evidence(opp: Opportunity) -> list[dict]:
    out: list[dict] = []
    for i, es in enumerate(opp.event.sources if opp.event and opp.event.sources else [], start=1):
        out.append({"id": f"S{i}", "tier": "fact",
                    "statement": es.snippet or es.source_url,
                    "snippet": es.snippet, "source_url": es.source_url,
                    "confidence": float(es.confidence) if es.confidence is not None else None})
    for i, ev in enumerate(opp.evidence if opp.evidence else [], start=1):
        out.append({"id": f"E{i}", "tier": "inference" if ev.evidence_type.value == "rule_match" else "fact",
                    "statement": ev.description or "", "snippet": None,
                    "source_url": ev.source_url,
                    "confidence": float(ev.weight) if ev.weight is not None else None})
    return out


def _sources(opp: Opportunity) -> list[dict]:
    out = []
    for es in opp.event.sources if opp.event and opp.event.sources else []:
        rd = es.raw_document
        gs = es.government_source
        out.append({"title": (rd.title if rd and rd.title else es.source_url),
                    "url": es.source_url,
                    "kind": gs.source_type.value if gs else None,
                    "date": rd.fetched_at.date().isoformat() if rd and rd.fetched_at else None})
    return out


_BRIEF_INFERRED = "_(inferred)_"


def _parse_brief(content: str) -> tuple[list[dict], str | None]:
    """Parse rendered brief markdown (self-authored format) back into sections."""
    sections: list[dict] = []
    risk: str | None = None
    if not content:
        return sections, risk
    for block in content.split("\n## "):
        block = block.lstrip("# ").strip()
        if not block:
            continue
        head, _, body = block.partition("\n")
        is_inference = _BRIEF_INFERRED in head
        title = head.replace(_BRIEF_INFERRED, "").strip()
        text = body.strip()
        if title.lower().startswith("flags"):
            continue
        if title.lower().startswith("risk"):
            risk = text
            continue
        sections.append({"key": _slug(title), "title": title, "text": text, "is_inference": is_inference})
    return sections, risk


def _kb_detail(opp: Opportunity, kb: KnowledgeBase) -> dict:
    rule = _kb_rule(opp, kb)
    need = rule.business_needs[0] if rule and rule.business_needs else None
    return {
        "need": opp.title,
        "reasoning": opp.rationale,
        "assumptions": list(need.assumptions) if need else [],
        "alternatives": list(need.alternatives) if need else [],
        "timing": need.timing if need else None,
        "departments": list(rule.departments) if rule else [],
        "job_titles": list(rule.job_titles) if rule else [],
        "tier": (need.tier.name if need else "inference"),
    }


def build_summary(opp: Opportunity, kb: KnowledgeBase) -> dict:
    ls = _current_score(opp)
    detail = _kb_detail(opp, kb)
    contact = _best_contact(opp.company) if opp.company else None
    product = opp.product.name if opp.product else opp.title
    ev = _event_dict(opp.event) if opp.event else {}
    days = None
    if opp.event and opp.event.event_date:
        days = (date.today() - opp.event.event_date).days
    why_now = (f"{ev.get('type_label', 'Event')} dated {ev.get('date')}"
               + (f" ({days} days ago)" if days is not None else "") + ".")
    company_name = opp.company.canonical_name if opp.company else "The company"
    sector = ev.get("sector")
    sponsorship_like = opp.opportunity_type in (
        OpportunityType.sponsorship, OpportunityType.event_participation, OpportunityType.advertising,
    )
    if sponsorship_like:
        event_name = product.split(" — ")[0].split(" - ")[0]  # drop the "— Sponsorship" suffix
        won = (f"just won government business in {sector}" if sector else "just won government business")
        reason = (f"{company_name} {won} — congratulate them on the "
                  f"{ev.get('type_label', 'award').lower()} and invite them to sponsor {event_name}.")
    else:
        reason = (f"{company_name} may have a "
                  f"{opp.title.lower()} after this {ev.get('type_label', 'event').lower()} — a fit for {product}.")
    target = (contact.full_name if contact and contact.is_verified
              else (detail["job_titles"][0] if detail["job_titles"] else "decision-maker"))
    return {
        "id": str(opp.id), "company": opp.company.canonical_name if opp.company else "Unknown",
        "status": opp.status.value, "event": ev,
        "opportunity": product, "opportunity_tier": detail["tier"],
        "score": int(ls.score) if ls else 0,
        "grade": (ls.grade.value if ls and ls.grade else "F"),
        "confidence": float(opp.confidence) if opp.confidence is not None else 0.0,
        "why_now": why_now, "reason_to_call": reason, "target_contact": target,
    }


def build_detail(opp: Opportunity, kb: KnowledgeBase) -> dict:
    lead = build_summary(opp, kb)
    ls = _current_score(opp)
    components = (ls.factors or {}).get("components", []) if ls else []
    brief_row = None
    if opp.briefs:
        brief_row = sorted(opp.briefs, key=lambda b: b.generated_at)[-1]
    brief_sections, risk = _parse_brief(brief_row.content if brief_row else "")
    contact = _best_contact(opp.company) if opp.company else None
    detail = _kb_detail(opp, kb)
    lead.update({
        "company_profile": _company_profile(opp.company) if opp.company else {},
        "opportunity_detail": detail,
        "evidence": _evidence(opp),
        "score_components": [{"key": c.get("key"), "points": c.get("points"),
                              "max_points": c.get("max_points"), "note": c.get("explanation")}
                             for c in components],
        "contact": (None if contact is None else {
            "name": contact.full_name, "title": contact.title, "verified": contact.is_verified,
            "email": contact.email, "linkedin": contact.linkedin_url,
            "source": contact.source.value if contact.source else None,
            "confidence": float(contact.confidence) if contact.confidence is not None else None}),
        "brief": brief_sections, "risk": risk, "sources": _sources(opp),
    })
    return lead


# --------------------------------------------------------------------------- #
# Repository
# --------------------------------------------------------------------------- #
def _matches(summary: dict, filters: dict) -> bool:
    if summary["score"] < filters.get("score_min", 0):
        return False
    ev = summary["event"]
    if (s := filters.get("sector")) and ev.get("sector") != s:
        return False
    if (p := filters.get("product")) and summary["opportunity"] != p:
        return False
    if (et := filters.get("event_type")) and ev.get("type_label") != et:
        return False
    if (org := filters.get("gov_org")) and ev.get("org") != org:
        return False
    if (st := filters.get("status")) and summary["status"] != st:
        return False
    if (co := filters.get("company")) and co.lower() not in summary["company"].lower():
        return False
    if (dd := filters.get("date_days")) and ev.get("date"):
        try:
            if (date.today() - date.fromisoformat(ev["date"])).days > dd:
                return False
        except ValueError:
            return False
    return True


class SqlAlchemyLeadRepository:
    def __init__(self, session_factory: Callable[[], Session], *, knowledge_base: KnowledgeBase | None = None) -> None:
        self._session_factory = session_factory
        self._kb = knowledge_base or default_knowledge_base()

    def list_leads(self, organization_id: str, filters: dict) -> list[dict]:
        try:
            org = uuid.UUID(organization_id)
        except (ValueError, TypeError):
            return []
        with self._session_factory() as session:
            stmt = (select(Opportunity)
                    .where(Opportunity.organization_id == org)
                    .options(selectinload(Opportunity.event).selectinload(GovernmentEvent.sources),
                             selectinload(Opportunity.company).selectinload(Company.contacts),
                             selectinload(Opportunity.product),
                             selectinload(Opportunity.lead_scores)))
            opps = session.scalars(stmt).all()
            leads = [build_summary(o, self._kb) for o in opps]
            leads = [l for l in leads if _matches(l, filters)]
            leads.sort(key=lambda x: x["score"], reverse=True)
            return leads

    def get_lead(self, organization_id: str, lead_id: str) -> dict | None:
        try:
            org, lid = uuid.UUID(organization_id), uuid.UUID(lead_id)
        except (ValueError, TypeError):
            return None
        with self._session_factory() as session:
            stmt = (select(Opportunity).where(Opportunity.id == lid)
                    .options(selectinload(Opportunity.event).selectinload(GovernmentEvent.sources),
                             selectinload(Opportunity.company).selectinload(Company.contacts),
                             selectinload(Opportunity.company).selectinload(Company.enrichments),
                             selectinload(Opportunity.product),
                             selectinload(Opportunity.lead_scores),
                             selectinload(Opportunity.briefs),
                             selectinload(Opportunity.evidence)))
            opp = session.scalars(stmt).first()
            if opp is None or opp.organization_id != org:
                return None
            return build_detail(opp, self._kb)

    def record_feedback(self, organization_id: str, lead_id: str,
                        event_type: FeedbackEventType, note: str | None, actor: str) -> dict:
        try:
            org, lid = uuid.UUID(organization_id), uuid.UUID(lead_id)
        except (ValueError, TypeError):
            return {"ok": False, "reason": "not_found"}
        with self._session_factory() as session:
            opp = session.get(Opportunity, lid)
            if opp is None or opp.organization_id != org:
                return {"ok": False, "reason": "not_found"}
            _record_feedback_row(session, event_type=event_type, opportunity_id=opp.id,
                                 note=f"actor={actor}; {note or ''}".strip())
            new_status = _FEEDBACK_STATUS.get(event_type)
            if new_status is not None:
                opp.status = new_status
            session.commit()
            return {"ok": True, "status": opp.status.value}
