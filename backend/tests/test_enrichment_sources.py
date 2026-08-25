"""Enrichment source-adapter tests (all with fake injected clients)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.enrichment.sources.base import Article, FetchDoc
from app.enrichment.sources.news import NewsSource
from app.enrichment.sources.registry import RegistrySource
from app.enrichment.sources.website import WebsiteSource
from app.enrichment.types import CompanyRef, EnrichmentField, SourceTier

NOW = datetime(2026, 8, 25, tzinfo=timezone.utc)


def _now() -> datetime:
    return NOW


# --- website (first-party) ---------------------------------------------------
class FakeFetcher:
    def __init__(self, docs: dict[str, FetchDoc]) -> None:
        self._docs = docs

    def get(self, url: str) -> FetchDoc | None:
        return self._docs.get(url)


JSON_LD_HTML = """
<html><head>
<script type="application/ld+json">
{"@type":"Organization","name":"Acme","description":"Acme builds smart-city command centres.",
 "address":{"addressLocality":"Pune","addressRegion":"Maharashtra"}}
</script></head><body>Home</body></html>
"""


def test_website_extracts_first_party_json_ld() -> None:
    fetcher = FakeFetcher({"https://acme.example/": FetchDoc("https://acme.example/", 200, JSON_LD_HTML)})
    src = WebsiteSource(fetcher, now=_now)
    claims = src.collect(CompanyRef("Acme", website="https://acme.example/"))
    by_field = {c.field: c for c in claims}

    assert by_field[EnrichmentField.website].tier is SourceTier.first_party
    assert "smart-city" in by_field[EnrichmentField.business_description].value
    assert "Pune" in by_field[EnrichmentField.hq_location].value
    # every claim carries provenance
    for c in claims:
        assert c.source_url and c.retrieved_at == NOW and c.evidence


def test_website_meta_description_fallback() -> None:
    html = '<html><head><meta name="description" content="Beta Ltd provides logistics."></head></html>'
    fetcher = FakeFetcher({"https://beta.example": FetchDoc("https://beta.example", 200, html)})
    src = WebsiteSource(fetcher, now=_now)
    claims = src.collect(CompanyRef("Beta", domain="beta.example"))
    desc = next(c for c in claims if c.field is EnrichmentField.business_description)
    assert desc.value == "Beta Ltd provides logistics."


def test_website_no_target_or_error_returns_nothing() -> None:
    assert WebsiteSource(FakeFetcher({}), now=_now).collect(CompanyRef("NoSite")) == []
    fetcher = FakeFetcher({"https://x.example": FetchDoc("https://x.example", 404, "")})
    assert WebsiteSource(fetcher, now=_now).collect(CompanyRef("X", website="https://x.example")) == []


# --- registry (authoritative) ------------------------------------------------
class FakeRegistry:
    def __init__(self, record: dict | None) -> None:
        self._record = record

    def lookup(self, *, cin=None, gstin=None, name=None) -> dict | None:
        return self._record


def test_registry_emits_authoritative_claims() -> None:
    record = {
        "industry": "Information Technology",
        "hq_location": "Bengaluru, Karnataka",
        "employee_range": "1001-5000",
        "subsidiaries": ["Acme Cloud Pvt Ltd", "Acme Labs Pvt Ltd"],
        "source_url": "https://mca.gov.in/company/U123",
    }
    src = RegistrySource(FakeRegistry(record), now=_now)
    claims = src.collect(CompanyRef("Acme", cin="U123"))
    fields = {c.field for c in claims}
    assert EnrichmentField.industry in fields
    assert EnrichmentField.employee_range in fields
    subs = [c.value for c in claims if c.field is EnrichmentField.subsidiaries]
    assert len(subs) == 2
    assert all(c.tier is SourceTier.authoritative for c in claims)


def test_registry_no_match_returns_nothing() -> None:
    assert RegistrySource(FakeRegistry(None), now=_now).collect(CompanyRef("Acme", cin="U1")) == []


# --- news (reputable) --------------------------------------------------------
class FakeNews:
    def __init__(self, articles: list[Article]) -> None:
        self._articles = articles

    def search(self, query: str) -> list[Article]:
        return self._articles


def test_news_classifies_signals() -> None:
    articles = [
        Article("Acme bags order worth INR 50 cr", "https://n1", "Acme was awarded a contract by NHAI.",
                source_name="Economic Times"),
        Article("Acme raised Series B funding", "https://n2", "Acme raised investment of $20M."),
        Article("Acme sets up new plant in Pune", "https://n3", "Expansion of manufacturing capacity."),
    ]
    src = NewsSource(FakeNews(articles), now=_now)
    claims = src.collect(CompanyRef("Acme"))
    fields = {c.field for c in claims}
    assert EnrichmentField.recent_contracts in fields
    assert EnrichmentField.funding_signals in fields
    assert EnrichmentField.expansion_activity in fields
    # every article also counts as a general announcement
    ann = [c for c in claims if c.field is EnrichmentField.recent_announcements]
    assert len(ann) == 3
    # provenance retained (URL + evidence)
    contract = next(c for c in claims if c.field is EnrichmentField.recent_contracts)
    assert contract.source_url == "https://n1" and contract.evidence
