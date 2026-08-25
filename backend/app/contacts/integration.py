"""Bridges: build a query from an opportunity; hand a contact to the brief."""
from __future__ import annotations

from typing import Any

from app.brief.types import ContactInfo
from app.contacts.types import ContactCandidate, ContactQuery
from app.opportunity.types import Opportunity


def contact_query_from_opportunity(
    opportunity: Opportunity, *, company_name: str, company_id: Any = None, domain: str | None = None
) -> ContactQuery:
    return ContactQuery(
        company_name=company_name,
        company_id=company_id,
        domain=domain,
        target_titles=list(opportunity.job_titles),
        target_departments=list(opportunity.departments),
    )


def to_contact_info(candidate: ContactCandidate) -> ContactInfo:
    return ContactInfo(
        name=candidate.name,
        title=candidate.title,
        seniority=candidate.seniority,
        email=candidate.email,
        phone=candidate.phone,
        linkedin_url=candidate.linkedin_url,
        source_url=candidate.source_url,
        confidence=candidate.confidence,
        verified=candidate.verified,
    )
