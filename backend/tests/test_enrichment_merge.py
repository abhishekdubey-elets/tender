"""Merge logic: authority priority, corroboration, conflict, unknowns."""
from __future__ import annotations

from datetime import datetime, timezone

from app.enrichment.merge import merge_claims
from app.enrichment.types import Claim, EnrichmentField, SourceTier

NOW = datetime(2026, 8, 25, tzinfo=timezone.utc)


def mk(field, value, *, tier=SourceTier.reputable, conf=0.7, name="s", url="https://s") -> Claim:
    return Claim(field, value, name, url, tier, NOW, "evidence", conf)


def test_unknown_when_no_claims() -> None:
    profile, _ = merge_claims([])
    fr = profile[EnrichmentField.revenue]
    assert fr.status == "unknown" and fr.value is None and fr.confidence == 0.0


def test_authoritative_beats_lower_tier_on_conflict() -> None:
    claims = [
        mk(EnrichmentField.industry, "Information Technology", tier=SourceTier.authoritative, conf=0.9, name="registry"),
        mk(EnrichmentField.industry, "Software Services", tier=SourceTier.aggregator, conf=0.5, name="db"),
    ]
    profile, warnings = merge_claims(claims)
    fr = profile[EnrichmentField.industry]
    assert fr.value == "Information Technology"     # higher authority wins
    assert fr.conflict is True
    assert fr.confidence < 0.9                        # conflict lowers confidence
    assert any("industry" in w for w in warnings)


def test_agreement_raises_confidence() -> None:
    claims = [
        mk(EnrichmentField.industry, "IT", tier=SourceTier.authoritative, conf=0.9, name="registry"),
        mk(EnrichmentField.industry, "IT", tier=SourceTier.reputable, conf=0.7, name="news"),
    ]
    profile, _ = merge_claims(claims)
    fr = profile[EnrichmentField.industry]
    assert fr.conflict is False
    assert fr.confidence > 0.9                         # corroboration boost


def test_list_fields_union_and_dedupe() -> None:
    claims = [
        mk(EnrichmentField.recent_contracts, "Won NHAI road contract", url="https://a"),
        mk(EnrichmentField.recent_contracts, "Won metro contract", url="https://b"),
        mk(EnrichmentField.recent_contracts, "won nhai road contract", url="https://c"),  # dup (normalized)
    ]
    profile, _ = merge_claims(claims)
    fr = profile[EnrichmentField.recent_contracts]
    assert fr.status == "known"
    assert len(fr.value) == 2                          # deduped
    assert all("source_url" in item and "retrieved_at" in item for item in fr.value)
