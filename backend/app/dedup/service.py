"""EventDeduplicator: turns a stream of candidate events into canonical events
+ linked source evidence, using an injected CandidateProvider (what already
exists) and EventStore (how to create/link). Storage stays behind interfaces so
the core is testable without a database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.dedup.fingerprint import EventFingerprint
from app.dedup.matcher import EventMatcher


@runtime_checkable
class CandidateProvider(Protocol):
    def candidates(self, fingerprint: EventFingerprint) -> list[tuple[Any, EventFingerprint]]: ...


@runtime_checkable
class EventStore(Protocol):
    def create_canonical(self, payload: Any, fingerprint: EventFingerprint, context: Any) -> Any: ...

    def link_source(self, ref: Any, payload: Any, context: Any) -> None: ...


@dataclass(slots=True)
class DedupDecision:
    index: int
    matched: bool
    ref: Any
    method: str | None
    confidence: float
    reason: str | None = None


class EventDeduplicator:
    def __init__(self, matcher: EventMatcher, provider: CandidateProvider, store: EventStore) -> None:
        self._matcher = matcher
        self._provider = provider
        self._store = store

    def process(
        self, items: list[tuple[EventFingerprint, Any]], context: Any = None
    ) -> list[DedupDecision]:
        decisions: list[DedupDecision] = []
        for index, (fingerprint, payload) in enumerate(items):
            existing = self._provider.candidates(fingerprint)
            match = self._matcher.find_match(fingerprint, existing)
            if match.matched:
                # Same underlying event → attach this document as new evidence.
                self._store.link_source(match.ref, payload, context)
                decisions.append(
                    DedupDecision(index, True, match.ref, match.method, match.confidence, match.reason)
                )
            else:
                ref = self._store.create_canonical(payload, fingerprint, context)
                decisions.append(DedupDecision(index, False, ref, "new", 1.0, "new canonical"))
        return decisions


# --------------------------------------------------------------------------- #
# In-memory implementations (tests / batch use)
# --------------------------------------------------------------------------- #
@dataclass
class _Canonical:
    ref: int
    payload: Any
    fingerprint: EventFingerprint
    sources: list[Any] = field(default_factory=list)


class InMemoryEventStore:
    def __init__(self) -> None:
        self.canonicals: dict[int, _Canonical] = {}
        self._next = 1

    def create_canonical(self, payload: Any, fingerprint: EventFingerprint, context: Any = None) -> int:
        ref = self._next
        self._next += 1
        self.canonicals[ref] = _Canonical(ref, payload, fingerprint, sources=[payload])
        return ref

    def link_source(self, ref: int, payload: Any, context: Any = None) -> None:
        self.canonicals[ref].sources.append(payload)  # evidence appended, never replaced

    def fingerprints(self) -> list[tuple[int, EventFingerprint]]:
        return [(ref, c.fingerprint) for ref, c in self.canonicals.items()]


class InMemoryCandidateProvider:
    def __init__(self, store: InMemoryEventStore) -> None:
        self._store = store

    def candidates(self, fingerprint: EventFingerprint) -> list[tuple[int, EventFingerprint]]:
        return self._store.fingerprints()
