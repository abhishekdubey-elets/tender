"""PART A — event deduplication: deterministic + semantic, false pos/neg."""
from __future__ import annotations

from datetime import date

from app.dedup.fingerprint import EventFingerprint
from app.dedup.matcher import EventMatcher, HashingEmbedder
from app.dedup.normalize import normalize_identifier
from app.dedup.service import (
    EventDeduplicator,
    InMemoryCandidateProvider,
    InMemoryEventStore,
)


def fp(**kw) -> EventFingerprint:
    return EventFingerprint.build(**kw)


def test_normalize_identifier() -> None:
    assert normalize_identifier("GEM/2026/B/12345") == "GEM2026B12345"
    assert normalize_identifier("gem 2026 b 12345") == "GEM2026B12345"
    assert normalize_identifier(None) is None


# --- deterministic: identifier ----------------------------------------------
def test_shared_identifier_matches_despite_other_differences() -> None:
    m = EventMatcher()
    a = fp(identifiers=["GEM/2026/B/123"], buyer="Ministry A", company="Acme Ltd",
           value=100, event_date=date(2026, 8, 1))
    b = fp(identifiers=["gem 2026 b 123"], buyer="Totally Different", company="Other Co",
           value=999, event_date=date(2020, 1, 1))
    result = m.find_match(a, [(1, b)])
    assert result.matched and result.method == "identifier"


# --- deterministic: composite -----------------------------------------------
def test_composite_matches_same_event_with_minor_variation() -> None:
    m = EventMatcher()
    a = fp(buyer="Ministry of X", company="Acme Ltd", value=1_000_000, event_date=date(2026, 8, 1))
    b = fp(buyer="ministry of x", company="acme ltd", value=1_000_005, event_date=date(2026, 8, 2))
    result = m.find_match(a, [(7, b)])
    assert result.matched and result.method == "composite"
    assert result.ref == 7


# --- FALSE POSITIVES (must NOT match) ---------------------------------------
def test_false_positive_different_company_not_matched() -> None:
    m = EventMatcher()  # no embedder → deterministic only
    a = fp(buyer="Ministry of X", company="Acme Ltd", value=1_000_000, event_date=date(2026, 8, 1))
    b = fp(buyer="Ministry of X", company="Beta Ltd", value=1_000_000, event_date=date(2026, 8, 1))
    assert not m.find_match(a, [(1, b)]).matched


def test_false_positive_value_far_apart_not_matched() -> None:
    m = EventMatcher()
    a = fp(buyer="Ministry of X", company="Acme Ltd", value=1_000_000, event_date=date(2026, 8, 1))
    b = fp(buyer="Ministry of X", company="Acme Ltd", value=5_000_000, event_date=date(2026, 8, 1))
    assert not m.find_match(a, [(1, b)]).matched


def test_false_positive_buyer_company_only_insufficient() -> None:
    m = EventMatcher()
    a = fp(buyer="Ministry of X", company="Acme Ltd")   # no value/date corroboration
    b = fp(buyer="Ministry of X", company="Acme Ltd")
    assert not m.find_match(a, [(1, b)]).matched


# --- semantic (fallback only) ----------------------------------------------
def test_semantic_match_when_no_deterministic_signal() -> None:
    m = EventMatcher(HashingEmbedder(), semantic_threshold=0.8)
    a = fp(company="Acme Ltd", text="smart city command centre contract awarded pune")
    b = fp(company="Acme Ltd", text="smart city command centre contract awarded pune")
    result = m.find_match(a, [(1, b)])
    assert result.matched and result.method == "semantic"


def test_false_positive_semantic_unrelated_not_matched() -> None:
    m = EventMatcher(HashingEmbedder(), semantic_threshold=0.8)
    a = fp(company="Acme Ltd", text="smart city command centre contract awarded pune")
    b = fp(company="Zeta Corp", text="annual rainfall monsoon agricultural advisory report")
    assert not m.find_match(a, [(1, b)]).matched


# --- deduplicator: one canonical + many sources -----------------------------
def test_deduplicator_collapses_same_event_keeps_all_sources() -> None:
    store = InMemoryEventStore()
    dedup = EventDeduplicator(EventMatcher(), InMemoryCandidateProvider(store), store)

    a = fp(identifiers=["T-100"], buyer="Min", company="Acme", value=100, event_date=date(2026, 8, 1))
    b = fp(identifiers=["T 100"], buyer="Min", company="Acme", value=100, event_date=date(2026, 8, 1))
    decisions = dedup.process([(a, "gem_doc"), (b, "news_doc")])

    assert decisions[0].matched is False           # first creates canonical
    assert decisions[1].matched is True            # second linked as evidence
    assert len(store.canonicals) == 1              # one canonical event
    only = next(iter(store.canonicals.values()))
    assert only.sources == ["gem_doc", "news_doc"]  # both sources preserved


def test_deduplicator_keeps_distinct_events_separate() -> None:
    store = InMemoryEventStore()
    dedup = EventDeduplicator(EventMatcher(), InMemoryCandidateProvider(store), store)
    a = fp(identifiers=["T-1"], buyer="Min", company="Acme", value=1, event_date=date(2026, 8, 1))
    b = fp(identifiers=["T-2"], buyer="Min", company="Beta", value=2, event_date=date(2026, 8, 2))
    dedup.process([(a, "d1"), (b, "d2")])
    assert len(store.canonicals) == 2
