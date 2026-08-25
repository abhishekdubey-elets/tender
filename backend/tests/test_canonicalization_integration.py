"""Integration: extraction output → dedup + company resolution (in-memory)."""
from __future__ import annotations

from datetime import date

from app.canonicalization import canonicalize_extracted
from app.dedup.matcher import EventMatcher
from app.dedup.service import (
    EventDeduplicator,
    InMemoryCandidateProvider,
    InMemoryEventStore,
)
from app.extraction.schema import EntityRef, EventIdentifiers, ExtractedEvent
from app.resolution.matcher import CompanyMatcher
from app.resolution.service import (
    CompanyResolver,
    InMemoryCompanyProvider,
    InMemoryCompanyStore,
)


def _event(tender: str, awardee_name: str) -> ExtractedEvent:
    return ExtractedEvent(
        event_type="contract_award",
        identifiers=EventIdentifiers(tender_number=tender),
        government_entity="Ministry of Roads",
        entities=[EntityRef(name=awardee_name, role="awardee")],
        contract_value=5_000_000,
        award_date=date(2026, 8, 1),
        confidence=0.9,
    )


def test_same_event_from_two_sources_one_canonical_one_company() -> None:
    # Two documents describing the SAME award (same tender), awardee written two
    # different ways.
    events = [
        _event("T-100", "M/s Acme Infra Pvt Ltd"),
        _event("T 100", "Acme Infra Private Limited"),
    ]

    event_store = InMemoryEventStore()
    deduper = EventDeduplicator(
        EventMatcher(), InMemoryCandidateProvider(event_store), event_store
    )
    company_store = InMemoryCompanyStore()
    resolver = CompanyResolver(
        CompanyMatcher(), InMemoryCompanyProvider(company_store), company_store
    )

    report = canonicalize_extracted(events, deduplicator=deduper, resolver=resolver)

    # PART A: one canonical event, both documents preserved as sources.
    assert [d.matched for d in report.dedup] == [False, True]
    assert len(event_store.canonicals) == 1
    assert len(next(iter(event_store.canonicals.values())).sources) == 2

    # PART B: the two awardee spellings resolve to a single company.
    assert len(company_store.records) == 1
    assert report.resolutions[0].ref == report.resolutions[1].ref
    assert report.resolutions[1].created is False


def test_distinct_events_and_companies_stay_separate() -> None:
    events = [
        _event("T-1", "Acme Infra Pvt Ltd"),
        _event("T-2", "Beta Constructions Ltd"),
    ]
    event_store = InMemoryEventStore()
    deduper = EventDeduplicator(
        EventMatcher(), InMemoryCandidateProvider(event_store), event_store
    )
    company_store = InMemoryCompanyStore()
    resolver = CompanyResolver(
        CompanyMatcher(), InMemoryCompanyProvider(company_store), company_store
    )

    canonicalize_extracted(events, deduplicator=deduper, resolver=resolver)
    assert len(event_store.canonicals) == 2
    assert len(company_store.records) == 2
