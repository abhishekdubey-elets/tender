"""Relationship / cardinality tests for the key pipeline requirements."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import EvidenceType, OpportunityType
from app.db.models import (
    EventSource,
    OpportunityEvidence,
    Product,
    RawDocument,
    TargetSector,
)
from tests import factories as f


def test_multiple_sources_refer_to_one_event(session: Session) -> None:
    """Requirement: several sources may evidence the same event."""
    src_a = f.make_source(session, "pib")
    src_b = f.make_source(session, "eproc")
    doc_a = f.make_raw_document(session, src_a, url="https://pib.gov.in/x", content="a")
    doc_b = f.make_raw_document(session, src_b, url="https://eprocure.gov.in/y", content="b")
    event = f.make_event(session)

    f.link_event_source(session, event, doc_a, confidence=0.8)
    f.link_event_source(session, event, doc_b, confidence=0.95)

    session.refresh(event)
    assert len(event.sources) == 2
    # Both original URLs are preserved on the evidence rows.
    urls = {es.source_url for es in event.sources}
    assert urls == {"https://pib.gov.in/x", "https://eprocure.gov.in/y"}


def test_multiple_opportunities_from_one_event(session: Session) -> None:
    """Requirement: one event can generate many opportunities."""
    org = f.make_org(session, "multi-opp")
    event = f.make_event(session)
    company = f.make_company(session)

    f.make_opportunity(session, org, event, company, opportunity_type=OpportunityType.sponsorship)
    f.make_opportunity(session, org, event, company, opportunity_type=OpportunityType.advertising)

    session.refresh(event)
    assert len(event.opportunities) == 2


def test_multiple_products_per_organization_and_sector_m2m(session: Session) -> None:
    """Requirement: multiple products per org; products <-> sectors many-to-many."""
    org = f.make_org(session, "prod-org")
    sector1 = TargetSector(organization_id=org.id, name="Smart Cities")
    sector2 = TargetSector(organization_id=org.id, name="BFSI")
    session.add_all([sector1, sector2])
    session.flush()

    p1 = Product(organization_id=org.id, name="Summit Sponsorship")
    p1.target_sectors = [sector1, sector2]
    p2 = Product(organization_id=org.id, name="Magazine Ads")
    p2.target_sectors = [sector1]
    session.add_all([p1, p2])
    session.flush()

    session.refresh(org)
    assert len(org.products) == 2
    assert {s.name for s in p1.target_sectors} == {"Smart Cities", "BFSI"}
    # Reverse side of the m2m works too.
    session.refresh(sector1)
    assert len(sector1.products) == 2


def test_deleting_event_keeps_raw_document(session: Session) -> None:
    """Cascade deletes evidence links but never the authoritative raw document."""
    src = f.make_source(session, "cascade")
    doc = f.make_raw_document(session, src)
    event = f.make_event(session)
    f.link_event_source(session, event, doc)

    session.delete(event)
    session.flush()

    # Evidence link is gone...
    assert session.scalar(select(func.count()).select_from(EventSource)) == 0
    # ...but the raw document survives.
    assert session.get(RawDocument, doc.id) is not None


def test_opportunity_traceable_to_provenance(session: Session) -> None:
    """An opportunity's evidence can point back to the exact source URL."""
    org = f.make_org(session, "trace")
    src = f.make_source(session, "trace-src")
    doc = f.make_raw_document(session, src, url="https://gem.gov.in/award/42")
    event = f.make_event(session)
    es = f.link_event_source(session, event, doc)
    company = f.make_company(session)
    opp = f.make_opportunity(session, org, event, company)

    ev = OpportunityEvidence(
        opportunity_id=opp.id,
        evidence_type=EvidenceType.event_source,
        event_source_id=es.id,
        raw_document_id=doc.id,
        source_url=doc.source_url,
        description="Company won a GeM award",
        weight=0.9,
    )
    session.add(ev)
    session.flush()

    session.refresh(opp)
    assert len(opp.evidence) == 1
    assert opp.evidence[0].source_url == "https://gem.gov.in/award/42"
    assert opp.evidence[0].event_source.raw_document.source_url == "https://gem.gov.in/award/42"
