"""First-party source: the company's own website.

Prefers structured first-party data (schema.org Organization JSON-LD), falling
back to the meta description. Only emits claims for data actually present on the
page — never guesses.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone

from app.enrichment.sources.base import Fetcher, make_claim
from app.enrichment.types import Claim, CompanyRef, EnrichmentField, SourceTier


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WebsiteSource:
    name = "official_website"
    tier = SourceTier.first_party

    def __init__(self, fetcher: Fetcher, *, now: Callable[[], datetime] = _utcnow) -> None:
        self._fetcher = fetcher
        self._now = now

    def _target_url(self, ref: CompanyRef) -> str | None:
        if ref.website:
            return ref.website
        if ref.domain:
            return f"https://{ref.domain}"
        return None

    def collect(self, ref: CompanyRef) -> list[Claim]:
        url = self._target_url(ref)
        if not url:
            return []
        doc = self._fetcher.get(url)
        if doc is None or doc.status >= 400 or not doc.text:
            return []

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(doc.text, "html.parser")
        retrieved = self._now()
        claims: list[Claim] = []

        # The website itself is a first-party fact.
        claims.append(make_claim(
            field=EnrichmentField.website, value=doc.url, source_name=self.name,
            source_url=doc.url, tier=self.tier, retrieved_at=retrieved,
            evidence=doc.url, confidence=0.95,
        ))

        org = self._json_ld_org(soup)
        description = None
        if org:
            description = org.get("description")
            address = org.get("address") or {}
            if isinstance(address, dict):
                loc = " ".join(
                    str(address[k]) for k in ("addressLocality", "addressRegion", "addressCountry")
                    if address.get(k)
                ).strip()
                if loc:
                    claims.append(make_claim(
                        field=EnrichmentField.hq_location, value=loc, source_name=self.name,
                        source_url=doc.url, tier=self.tier, retrieved_at=retrieved,
                        evidence=json.dumps(address)[:300], confidence=0.85,
                    ))

        if not description:
            meta = soup.find("meta", attrs={"name": "description"})
            if meta and meta.get("content"):
                description = meta["content"].strip()

        if description:
            claims.append(make_claim(
                field=EnrichmentField.business_description, value=description,
                source_name=self.name, source_url=doc.url, tier=self.tier,
                retrieved_at=retrieved, evidence=description[:300], confidence=0.85,
            ))

        return claims

    @staticmethod
    def _json_ld_org(soup) -> dict | None:
        for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(tag.string or "")
            except (ValueError, TypeError):
                continue
            candidates = data if isinstance(data, list) else [data]
            for item in candidates:
                if isinstance(item, dict) and "Organization" in str(item.get("@type", "")):
                    return item
        return None
