"""Enrichment cache with TTL-based staleness (drives the refresh mechanism)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from app.enrichment.types import EnrichmentResult


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@runtime_checkable
class EnrichmentCache(Protocol):
    def get(self, key: str) -> EnrichmentResult | None: ...

    def set(self, key: str, result: EnrichmentResult) -> None: ...


@dataclass(slots=True)
class _Entry:
    result: EnrichmentResult
    stored_at: datetime


class InMemoryEnrichmentCache:
    """TTL cache. A stale entry is treated as a miss so the service re-fetches."""

    def __init__(self, ttl: timedelta | None = None, *, now: Callable[[], datetime] = _utcnow) -> None:
        self._ttl = ttl
        self._now = now
        self._store: dict[str, _Entry] = {}

    def get(self, key: str) -> EnrichmentResult | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if self._ttl is not None and (self._now() - entry.stored_at) > self._ttl:
            return None  # stale → miss
        return entry.result

    def set(self, key: str, result: EnrichmentResult) -> None:
        self._store[key] = _Entry(result=result, stored_at=self._now())

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def is_stale(self, key: str) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return True
        if self._ttl is None:
            return False
        return (self._now() - entry.stored_at) > self._ttl
