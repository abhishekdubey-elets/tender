"""Reputable source: recent news, classified into activity signals.

Each article is classified by keyword into contract/expansion/hiring/funding/
technology signals (and always recorded as a general announcement). Every signal
keeps the article URL + snippet as evidence.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.enrichment.sources.base import Article, NewsSearch, make_claim
from app.enrichment.types import Claim, CompanyRef, EnrichmentField, SourceTier

_SIGNAL_KEYWORDS: dict[EnrichmentField, tuple[str, ...]] = {
    EnrichmentField.recent_contracts: (
        "contract", "awarded", "work order", "tender", "bags order", "wins order", "order worth",
    ),
    EnrichmentField.expansion_activity: (
        "expansion", "expand", "new plant", "new facility", "sets up", "commissions", "capacity",
    ),
    EnrichmentField.hiring_signals: (
        "hiring", "recruit", "jobs", "headcount", "workforce", "onboard",
    ),
    EnrichmentField.funding_signals: (
        "funding", "raised", "investment", "series ", "ipo", "fundraise", "capital raise",
    ),
    EnrichmentField.technology_activity: (
        "technology", " ai ", "platform", "digital", "software", "launches", "r&d", "innovation",
    ),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NewsSource:
    name = "news"
    tier = SourceTier.reputable

    def __init__(self, search: NewsSearch, *, now: Callable[[], datetime] = _utcnow, max_articles: int = 25) -> None:
        self._search = search
        self._now = now
        self._max = max_articles

    def collect(self, ref: CompanyRef) -> list[Claim]:
        articles = self._search.search(ref.canonical_name)[: self._max]
        retrieved = self._now()
        claims: list[Claim] = []
        for article in articles:
            claims.extend(self._classify(article, retrieved))
        return claims

    def _classify(self, article: Article, retrieved: datetime) -> list[Claim]:
        haystack = f"{article.title} {article.snippet}".lower()
        out: list[Claim] = []

        # Always a general announcement.
        out.append(self._claim(EnrichmentField.recent_announcements, article, retrieved, 0.6))

        for field, keywords in _SIGNAL_KEYWORDS.items():
            if any(kw in haystack for kw in keywords):
                out.append(self._claim(field, article, retrieved, 0.65))
        return out

    def _claim(self, field: EnrichmentField, article: Article, retrieved: datetime, confidence: float) -> Claim:
        return make_claim(
            field=field,
            value=article.title,
            source_name=article.source_name or self.name,
            source_url=article.url,
            tier=self.tier,
            retrieved_at=article.published or retrieved,
            evidence=article.snippet[:300],
            confidence=confidence,
        )
