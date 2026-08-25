"""Domain types for enrichment."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class SourceTier(enum.IntEnum):
    """Authority ranking — higher wins when sources conflict."""

    unknown = 0
    aggregator = 1        # third-party company databases
    reputable = 2         # major news outlets
    authoritative = 3     # government registries, stock-exchange filings
    first_party = 4       # the company's own website / filings


class EnrichmentField(str, enum.Enum):
    website = "website"
    industry = "industry"
    hq_location = "hq_location"
    employee_range = "employee_range"
    revenue = "revenue"
    subsidiaries = "subsidiaries"
    business_description = "business_description"
    recent_announcements = "recent_announcements"
    recent_contracts = "recent_contracts"
    expansion_activity = "expansion_activity"
    hiring_signals = "hiring_signals"
    funding_signals = "funding_signals"
    technology_activity = "technology_activity"


SCALAR_FIELDS = {
    EnrichmentField.website,
    EnrichmentField.industry,
    EnrichmentField.hq_location,
    EnrichmentField.employee_range,
    EnrichmentField.revenue,
    EnrichmentField.business_description,
}

LIST_FIELDS = {
    EnrichmentField.subsidiaries,
    EnrichmentField.recent_announcements,
    EnrichmentField.recent_contracts,
    EnrichmentField.expansion_activity,
    EnrichmentField.hiring_signals,
    EnrichmentField.funding_signals,
    EnrichmentField.technology_activity,
}


@dataclass(slots=True)
class CompanyRef:
    """Input identity for enrichment."""

    canonical_name: str
    company_id: Any | None = None
    website: str | None = None
    domain: str | None = None
    cin: str | None = None
    gstin: str | None = None
    state: str | None = None
    city: str | None = None

    def cache_key(self) -> str:
        return str(self.company_id or self.domain or self.cin or self.canonical_name).lower()


@dataclass(slots=True)
class Claim:
    """A single field value with full provenance. The unit of grounded truth."""

    field: EnrichmentField
    value: Any
    source_name: str
    source_url: str
    tier: SourceTier
    retrieved_at: datetime
    evidence: str                    # verbatim snippet supporting the claim
    confidence: float


@dataclass(slots=True)
class FieldResult:
    field: EnrichmentField
    value: Any                       # scalar, or list of {value, source_url, ...}
    confidence: float
    status: str                      # "known" | "unknown"
    claims: list[Claim] = field(default_factory=list)
    conflict: bool = False

    @property
    def is_known(self) -> bool:
        return self.status == "known"


CompanyProfile = dict  # EnrichmentField -> FieldResult


@dataclass(slots=True)
class EnrichmentResult:
    company_ref: CompanyRef
    profile: dict
    generated_at: datetime
    from_cache: bool = False
    sources_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def field(self, name: EnrichmentField) -> FieldResult:
        return self.profile[name]
