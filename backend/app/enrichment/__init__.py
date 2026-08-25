"""Company Intelligence / enrichment service.

Given a canonical company, collects and normalizes publicly available
information from prioritized sources (first-party website and authoritative
registries first, then reputable news). Every claim retains its source URL,
retrieval time, an evidence snippet and a confidence. Nothing is invented — a
field with no grounded claim is returned as ``unknown``.

Source adapters are injected, so the service is fully testable without network.
"""
from __future__ import annotations

from app.enrichment.service import CompanyEnrichmentService
from app.enrichment.types import (
    Claim,
    CompanyProfile,
    CompanyRef,
    EnrichmentField,
    EnrichmentResult,
    FieldResult,
    SourceTier,
)

__all__ = [
    "CompanyEnrichmentService",
    "CompanyRef",
    "Claim",
    "EnrichmentField",
    "EnrichmentResult",
    "CompanyProfile",
    "FieldResult",
    "SourceTier",
]
