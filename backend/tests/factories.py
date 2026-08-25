"""Lightweight object factories for tests (no external deps)."""
from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.orm import Session

from app.db.enums import EventType, GovSourceType
from app.db.models import (
    Company,
    EventSource,
    GovernmentEvent,
    GovernmentSource,
    Opportunity,
    Organization,
    RawDocument,
    User,
)
from app.db.models.sources import AccessMethod


def make_org(session: Session, slug: str = "acme") -> Organization:
    org = Organization(name=f"Org {slug}", slug=slug)
    session.add(org)
    session.flush()
    return org


def make_user(session: Session, org: Organization, email: str = "u@acme.test") -> User:
    user = User(organization_id=org.id, email=email, full_name="Test User")
    session.add(user)
    session.flush()
    return user


def make_source(session: Session, slug: str = "src") -> GovernmentSource:
    src = GovernmentSource(
        name=f"Source {slug}",
        slug=slug,
        source_type=GovSourceType.eprocurement,
        base_url="https://example.gov.in/",
        access_method=AccessMethod.html,
    )
    session.add(src)
    session.flush()
    return src


def make_raw_document(
    session: Session,
    source: GovernmentSource,
    url: str = "https://example.gov.in/tender/1",
    content: str = "tender text",
) -> RawDocument:
    doc = RawDocument(
        government_source_id=source.id,
        source_url=url,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        raw_content=content,
    )
    session.add(doc)
    session.flush()
    return doc


def make_event(
    session: Session, title: str = "Award X", event_type: EventType = EventType.award
) -> GovernmentEvent:
    event = GovernmentEvent(event_type=event_type, title=title)
    session.add(event)
    session.flush()
    return event


def link_event_source(
    session: Session,
    event: GovernmentEvent,
    doc: RawDocument,
    confidence: float | None = 0.9,
) -> EventSource:
    es = EventSource(
        government_event_id=event.id,
        raw_document_id=doc.id,
        government_source_id=doc.government_source_id,
        source_url=doc.source_url,
        confidence=confidence,
    )
    session.add(es)
    session.flush()
    return es


def make_company(session: Session, name: str = "Acme Infra Pvt Ltd") -> Company:
    company = Company(canonical_name=name, normalized_name=name.lower())
    session.add(company)
    session.flush()
    return company


def make_opportunity(
    session: Session,
    org: Organization,
    event: GovernmentEvent,
    company: Company,
    product=None,
    opportunity_type=None,
    title: str = "Opportunity",
) -> Opportunity:
    kwargs = {}
    if product is not None:
        kwargs["product_id"] = product.id
    if opportunity_type is not None:
        kwargs["opportunity_type"] = opportunity_type
    opp = Opportunity(
        organization_id=org.id,
        government_event_id=event.id,
        company_id=company.id,
        title=title,
        **kwargs,
    )
    session.add(opp)
    session.flush()
    return opp


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
