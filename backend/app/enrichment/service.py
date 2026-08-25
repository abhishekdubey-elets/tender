"""CompanyEnrichmentService: orchestrate sources → merged, cached profile."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from app.enrichment.cache import EnrichmentCache
from app.enrichment.merge import merge_claims
from app.enrichment.sources.base import EnrichmentSource
from app.enrichment.types import CompanyRef, EnrichmentResult


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompanyEnrichmentService:
    def __init__(
        self,
        sources: list[EnrichmentSource],
        *,
        cache: EnrichmentCache | None = None,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        # Sources are consulted in order; higher-authority sources should come
        # first (their claims win ties during merge anyway, via tier).
        self._sources = sources
        self._cache = cache
        self._now = now

    def enrich(self, ref: CompanyRef, *, force_refresh: bool = False) -> EnrichmentResult:
        key = ref.cache_key()

        if self._cache is not None and not force_refresh:
            cached = self._cache.get(key)
            if cached is not None:
                return replace(cached, from_cache=True)

        claims = []
        sources_used: list[str] = []
        warnings: list[str] = []
        for source in self._sources:
            try:
                collected = source.collect(ref)
            except Exception as exc:  # noqa: BLE001 - isolate a failing source
                warnings.append(f"source '{getattr(source, 'name', '?')}' failed: {exc}")
                continue
            if collected:
                sources_used.append(source.name)
                claims.extend(collected)

        profile, merge_warnings = merge_claims(claims)
        warnings.extend(merge_warnings)

        result = EnrichmentResult(
            company_ref=ref,
            profile=profile,
            generated_at=self._now(),
            from_cache=False,
            sources_used=sources_used,
            warnings=warnings,
        )
        if self._cache is not None:
            self._cache.set(key, result)
        return result

    def refresh(self, ref: CompanyRef) -> EnrichmentResult:
        """Force a re-fetch, bypassing the cache."""
        return self.enrich(ref, force_refresh=True)
