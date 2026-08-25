"""Service orchestration: profile, unknowns, cache, refresh, staleness."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.enrichment.cache import InMemoryEnrichmentCache
from app.enrichment.service import CompanyEnrichmentService
from app.enrichment.types import Claim, CompanyRef, EnrichmentField, SourceTier

NOW = datetime(2026, 8, 25, tzinfo=timezone.utc)


def mk(field, value, *, tier=SourceTier.first_party, conf=0.9) -> Claim:
    return Claim(field, value, "s", "https://s", tier, NOW, "ev", conf)


class CountingSource:
    def __init__(self, name, tier, claims) -> None:
        self.name = name
        self.tier = tier
        self._claims = claims
        self.calls = 0

    def collect(self, ref: CompanyRef):
        self.calls += 1
        return list(self._claims)


class Clock:
    def __init__(self, start: datetime) -> None:
        self.t = start

    def now(self) -> datetime:
        return self.t

    def advance(self, delta: timedelta) -> None:
        self.t = self.t + delta


def _ref() -> CompanyRef:
    return CompanyRef("Acme", company_id="c1")


def test_profile_has_known_and_unknown_fields() -> None:
    src = CountingSource("web", SourceTier.first_party, [
        mk(EnrichmentField.website, "https://acme.example"),
        mk(EnrichmentField.business_description, "Acme builds systems."),
    ])
    result = CompanyEnrichmentService([src]).enrich(_ref())

    assert result.field(EnrichmentField.website).is_known
    assert result.field(EnrichmentField.website).confidence > 0
    # Nothing invented: unsupplied fields are unknown.
    assert result.field(EnrichmentField.revenue).status == "unknown"
    assert result.field(EnrichmentField.industry).status == "unknown"
    assert result.sources_used == ["web"]


def test_failing_source_is_isolated() -> None:
    class Boom:
        name = "boom"
        tier = SourceTier.reputable

        def collect(self, ref):
            raise RuntimeError("down")

    good = CountingSource("web", SourceTier.first_party, [mk(EnrichmentField.website, "https://a")])
    result = CompanyEnrichmentService([Boom(), good]).enrich(_ref())
    assert result.field(EnrichmentField.website).is_known
    assert any("boom" in w for w in result.warnings)


def test_cache_hit_avoids_recomputation() -> None:
    src = CountingSource("web", SourceTier.first_party, [mk(EnrichmentField.website, "https://a")])
    service = CompanyEnrichmentService([src], cache=InMemoryEnrichmentCache())

    first = service.enrich(_ref())
    second = service.enrich(_ref())
    assert first.from_cache is False
    assert second.from_cache is True
    assert src.calls == 1                       # source consulted only once


def test_refresh_forces_recompute() -> None:
    src = CountingSource("web", SourceTier.first_party, [mk(EnrichmentField.website, "https://a")])
    service = CompanyEnrichmentService([src], cache=InMemoryEnrichmentCache())
    service.enrich(_ref())
    refreshed = service.refresh(_ref())
    assert refreshed.from_cache is False
    assert src.calls == 2


def test_stale_cache_triggers_refetch() -> None:
    clock = Clock(NOW)
    src = CountingSource("web", SourceTier.first_party, [mk(EnrichmentField.website, "https://a")])
    cache = InMemoryEnrichmentCache(ttl=timedelta(hours=1), now=clock.now)
    service = CompanyEnrichmentService([src], cache=cache, now=clock.now)

    service.enrich(_ref())
    clock.advance(timedelta(minutes=30))
    assert service.enrich(_ref()).from_cache is True      # still fresh
    clock.advance(timedelta(hours=2))
    assert service.enrich(_ref()).from_cache is False     # stale → refetched
    assert src.calls == 2
