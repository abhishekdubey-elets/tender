"""Source-adapter protocols and shared helpers.

External clients (HTTP fetcher, news search, registry lookup) are injected so
adapters — and therefore the whole service — are testable without network.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.enrichment.types import Claim, CompanyRef, EnrichmentField, SourceTier


@dataclass(slots=True)
class FetchDoc:
    url: str
    status: int
    text: str
    content_type: str | None = None


@runtime_checkable
class Fetcher(Protocol):
    def get(self, url: str) -> FetchDoc | None: ...


@dataclass(slots=True)
class Article:
    title: str
    url: str
    snippet: str
    published: datetime | None = None
    source_name: str | None = None


@runtime_checkable
class NewsSearch(Protocol):
    def search(self, query: str) -> list[Article]: ...


@runtime_checkable
class RegistryClient(Protocol):
    def lookup(
        self, *, cin: str | None = None, gstin: str | None = None, name: str | None = None
    ) -> dict | None: ...


@runtime_checkable
class EnrichmentSource(Protocol):
    name: str
    tier: SourceTier

    def collect(self, ref: CompanyRef) -> list[Claim]: ...


def make_claim(
    *,
    field: EnrichmentField,
    value: object,
    source_name: str,
    source_url: str,
    tier: SourceTier,
    retrieved_at: datetime,
    evidence: str,
    confidence: float,
) -> Claim:
    return Claim(
        field=field,
        value=value,
        source_name=source_name,
        source_url=source_url,
        tier=tier,
        retrieved_at=retrieved_at,
        evidence=evidence,
        confidence=confidence,
    )
