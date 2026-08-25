"""Persist enrichment results into ``company_enrichment`` (and optionally fill
null core ``companies`` fields from high-authority claims).

One current row per provider (derived from source tier). Prior current rows for
the same provider are marked non-current so the partial-unique index
``(company_id, provider) WHERE is_current`` holds.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.enums import EnrichmentProvider
from app.db.models import Company, CompanyEnrichment
from app.enrichment.types import Claim, EnrichmentField, EnrichmentResult, SourceTier

_TIER_PROVIDER = {
    SourceTier.first_party: EnrichmentProvider.web,
    SourceTier.authoritative: EnrichmentProvider.registry,
    SourceTier.reputable: EnrichmentProvider.third_party,
    SourceTier.aggregator: EnrichmentProvider.third_party,
    SourceTier.unknown: EnrichmentProvider.other,
}


def _claim_dict(c: Claim) -> dict:
    return {
        "field": c.field.value,
        "value": c.value,
        "source_name": c.source_name,
        "source_url": c.source_url,
        "tier": c.tier.name,
        "retrieved_at": c.retrieved_at.isoformat(),
        "evidence": c.evidence,
        "confidence": c.confidence,
    }


def persist_enrichment(
    session: Session, company_id: Any, result: EnrichmentResult, *, update_company: bool = True
) -> list[CompanyEnrichment]:
    # Group all grounded claims by provider tier.
    by_provider: dict[EnrichmentProvider, list[Claim]] = {}
    for field_result in result.profile.values():
        for claim in field_result.claims:
            provider = _TIER_PROVIDER[claim.tier]
            by_provider.setdefault(provider, []).append(claim)

    rows: list[CompanyEnrichment] = []
    for provider, claims in by_provider.items():
        # Supersede the previous current row for this provider.
        session.execute(
            update(CompanyEnrichment)
            .where(
                CompanyEnrichment.company_id == company_id,
                CompanyEnrichment.provider == provider,
                CompanyEnrichment.is_current.is_(True),
            )
            .values(is_current=False)
        )
        industry = next((c.value for c in claims if c.field is EnrichmentField.industry), None)
        row = CompanyEnrichment(
            company_id=company_id,
            provider=provider,
            data={"claims": [_claim_dict(c) for c in claims]},
            industry=industry,
            confidence=round(max(c.confidence for c in claims), 3),
            fetched_at=max(c.retrieved_at for c in claims),
            is_current=True,
        )
        session.add(row)
        rows.append(row)

    if update_company:
        _fill_company_nulls(session, company_id, result)

    session.flush()
    return rows


def _fill_company_nulls(session: Session, company_id: Any, result: EnrichmentResult) -> None:
    company = session.get(Company, company_id)
    if company is None:
        return
    profile = result.profile

    def best(field: EnrichmentField) -> str | None:
        fr = profile.get(field)
        return fr.value if fr and fr.is_known and isinstance(fr.value, str) else None

    if company.website is None:
        company.website = best(EnrichmentField.website)
    if company.sector is None:
        company.sector = best(EnrichmentField.industry)
    if company.hq_state is None:
        company.hq_state = best(EnrichmentField.hq_location)
