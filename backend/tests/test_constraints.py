"""Constraint tests: unique keys, check constraints and NOT NULL provenance."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.enums import EventType
from app.db.models import (
    Company,
    GovernmentEvent,
    LeadScore,
    Organization,
    RawDocument,
    User,
)
from tests import factories as f


def test_organization_slug_unique(session: Session) -> None:
    session.add(Organization(name="A", slug="dup"))
    session.flush()
    session.add(Organization(name="B", slug="dup"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_user_email_case_insensitive_unique(session: Session) -> None:
    org = f.make_org(session, "case-org")
    session.add(User(organization_id=org.id, email="Person@Elets.in"))
    session.flush()
    session.add(User(organization_id=org.id, email="person@elets.in"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_raw_document_hash_unique_per_source(session: Session) -> None:
    src_a = f.make_source(session, "a")
    src_b = f.make_source(session, "b")
    f.make_raw_document(session, src_a, url="u1", content="same")
    # Same source + same content hash -> rejected.
    with session.begin_nested():
        with pytest.raises(IntegrityError):
            f.make_raw_document(session, src_a, url="u2", content="same")
    # Different source + same content hash -> allowed.
    f.make_raw_document(session, src_b, url="u3", content="same")


def test_company_cin_partial_unique(session: Session) -> None:
    session.add(Company(canonical_name="X", normalized_name="x", cin="U74999DL2020PTC000001"))
    session.add(Company(canonical_name="Y", normalized_name="y", cin=None))
    session.add(Company(canonical_name="Z", normalized_name="z", cin=None))  # two NULLs are fine
    session.flush()
    session.add(Company(canonical_name="W", normalized_name="w", cin="U74999DL2020PTC000001"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_confidence_range_check(session: Session) -> None:
    bad = GovernmentEvent(event_type=EventType.award, title="t", confidence=1.5)
    session.add(bad)
    with pytest.raises(IntegrityError):
        session.flush()


def test_dedup_key_partial_unique(session: Session) -> None:
    session.add(GovernmentEvent(event_type=EventType.award, title="a", dedup_key="k1"))
    # Multiple NULL dedup_keys are allowed.
    session.add(GovernmentEvent(event_type=EventType.tender, title="b"))
    session.add(GovernmentEvent(event_type=EventType.tender, title="c"))
    session.flush()
    session.add(GovernmentEvent(event_type=EventType.award, title="d", dedup_key="k1"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_one_current_lead_score_per_opportunity(session: Session) -> None:
    org = f.make_org(session, "ls-org")
    event = f.make_event(session)
    company = f.make_company(session)
    opp = f.make_opportunity(session, org, event, company)
    session.add(LeadScore(opportunity_id=opp.id, score=10, is_current=True))
    session.flush()
    # A second *current* score is rejected...
    with session.begin_nested():
        session.add(LeadScore(opportunity_id=opp.id, score=20, is_current=True))
        with pytest.raises(IntegrityError):
            session.flush()
    # ...but a historical (non-current) score is fine.
    session.add(LeadScore(opportunity_id=opp.id, score=20, is_current=False))
    session.flush()


def test_source_url_not_null(session: Session) -> None:
    src = f.make_source(session, "nn")
    doc = RawDocument(
        government_source_id=src.id,
        source_url=None,  # violates NOT NULL
        content_hash="abc",
    )
    session.add(doc)
    with pytest.raises(IntegrityError):
        session.flush()
