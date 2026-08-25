"""PART A — Event deduplication.

Detects when several documents (GeM, ministry site, PSU site, company press
release, news) refer to the same underlying government event. Deterministic
matching (strong identifiers, then a buyer/company/value/date composite) runs
first; semantic similarity is used only when deterministic matching is
insufficient. Evidence is never deleted — the result is **one canonical event +
many source documents**.
"""
from __future__ import annotations

from app.dedup.fingerprint import EventFingerprint
from app.dedup.matcher import EventMatcher, HashingEmbedder, MatchResult
from app.dedup.service import (
    CandidateProvider,
    DedupDecision,
    EventDeduplicator,
    EventStore,
    InMemoryCandidateProvider,
    InMemoryEventStore,
)

__all__ = [
    "EventFingerprint",
    "EventMatcher",
    "HashingEmbedder",
    "MatchResult",
    "EventDeduplicator",
    "DedupDecision",
    "CandidateProvider",
    "EventStore",
    "InMemoryCandidateProvider",
    "InMemoryEventStore",
]
