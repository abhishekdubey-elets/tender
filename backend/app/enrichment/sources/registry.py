"""Authoritative source: a company registry (e.g. MCA/CIN, GST, exchange filings).

The registry client is injected. Only fields actually returned by the registry
are emitted as claims; anything absent stays unknown.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone

from app.enrichment.sources.base import RegistryClient, make_claim
from app.enrichment.types import Claim, CompanyRef, EnrichmentField, SourceTier

# registry payload key -> scalar enrichment field
_SCALAR_KEYS = {
    "industry": EnrichmentField.industry,
    "hq_location": EnrichmentField.hq_location,
    "employee_range": EnrichmentField.employee_range,
    "revenue": EnrichmentField.revenue,
    "website": EnrichmentField.website,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RegistrySource:
    name = "company_registry"
    tier = SourceTier.authoritative

    def __init__(self, client: RegistryClient, *, now: Callable[[], datetime] = _utcnow) -> None:
        self._client = client
        self._now = now

    def collect(self, ref: CompanyRef) -> list[Claim]:
        if not (ref.cin or ref.gstin or ref.canonical_name):
            return []
        record = self._client.lookup(cin=ref.cin, gstin=ref.gstin, name=ref.canonical_name)
        if not record:
            return []

        source_url = record.get("source_url") or "registry://lookup"
        retrieved = self._now()
        claims: list[Claim] = []

        for key, field in _SCALAR_KEYS.items():
            value = record.get(key)
            if value:
                claims.append(make_claim(
                    field=field, value=value, source_name=self.name, source_url=source_url,
                    tier=self.tier, retrieved_at=retrieved,
                    evidence=f"{key}={value}", confidence=0.9,
                ))

        for subsidiary in record.get("subsidiaries", []) or []:
            claims.append(make_claim(
                field=EnrichmentField.subsidiaries, value=subsidiary, source_name=self.name,
                source_url=source_url, tier=self.tier, retrieved_at=retrieved,
                evidence=json.dumps(subsidiary)[:200] if not isinstance(subsidiary, str) else subsidiary,
                confidence=0.9,
            ))

        return claims
