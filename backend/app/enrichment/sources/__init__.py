"""Enrichment source adapters, ordered by authority (first-party → news)."""
from __future__ import annotations

from app.enrichment.sources.base import (
    Article,
    EnrichmentSource,
    FetchDoc,
    Fetcher,
    NewsSearch,
    RegistryClient,
)
from app.enrichment.sources.news import NewsSource
from app.enrichment.sources.registry import RegistrySource
from app.enrichment.sources.website import WebsiteSource

__all__ = [
    "EnrichmentSource",
    "Fetcher",
    "FetchDoc",
    "NewsSearch",
    "Article",
    "RegistryClient",
    "WebsiteSource",
    "RegistrySource",
    "NewsSource",
]
