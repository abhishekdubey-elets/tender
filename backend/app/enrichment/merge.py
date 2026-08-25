"""Merge claims from multiple sources into a company profile.

Rules:
  * a field with no claim → ``unknown`` (never invented);
  * scalar fields → the highest-authority claim wins; agreement across sources
    raises confidence; disagreement lowers it and flags a conflict;
  * list fields → union of distinct items, each keeping its own provenance.
"""
from __future__ import annotations

import re

from app.enrichment.types import (
    LIST_FIELDS,
    Claim,
    EnrichmentField,
    FieldResult,
)

_WS = re.compile(r"\s+")


def _norm(value: object) -> str:
    return _WS.sub(" ", str(value).strip().lower())


def _list_item(claim: Claim) -> dict:
    return {
        "value": claim.value,
        "source_name": claim.source_name,
        "source_url": claim.source_url,
        "retrieved_at": claim.retrieved_at.isoformat(),
        "evidence": claim.evidence,
        "confidence": claim.confidence,
    }


def merge_claims(claims: list[Claim]) -> tuple[dict, list[str]]:
    by_field: dict[EnrichmentField, list[Claim]] = {}
    for claim in claims:
        by_field.setdefault(claim.field, []).append(claim)

    profile: dict[EnrichmentField, FieldResult] = {}
    warnings: list[str] = []

    for field in EnrichmentField:
        field_claims = by_field.get(field, [])

        if not field_claims:
            profile[field] = FieldResult(field, None, 0.0, "unknown", [])
            continue

        if field in LIST_FIELDS:
            best_by_item: dict[str, Claim] = {}
            for claim in field_claims:
                key = _norm(claim.value)
                if key not in best_by_item or claim.confidence > best_by_item[key].confidence:
                    best_by_item[key] = claim
            kept = list(best_by_item.values())
            value = [_list_item(c) for c in kept]
            confidence = round(max(c.confidence for c in kept), 3)
            profile[field] = FieldResult(field, value, confidence, "known", kept)
            continue

        # Scalar: rank by (tier, confidence).
        best = max(field_claims, key=lambda c: (int(c.tier), c.confidence))
        agree = {c.source_name for c in field_claims if _norm(c.value) == _norm(best.value)}
        distinct_values = {_norm(c.value) for c in field_claims}

        confidence = min(0.99, best.confidence + 0.05 * (len(agree) - 1))
        conflict = len(distinct_values) > 1
        if conflict:
            confidence = max(0.3, confidence - 0.1)
            warnings.append(
                f"{field.value}: conflicting values across sources; kept "
                f"'{best.value}' from {best.source_name} (tier {best.tier.name})"
            )

        profile[field] = FieldResult(
            field, best.value, round(confidence, 3), "known", field_claims, conflict=conflict
        )

    return profile, warnings
