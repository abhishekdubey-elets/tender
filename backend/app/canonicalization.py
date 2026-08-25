"""Pipeline integration for event deduplication + company resolution.

Sits after extraction. For a document's extracted events it:
  1. deduplicates each event against existing canonical events (PART A), producing
     one canonical event + linked source evidence;
  2. resolves the awardee company of each event to a canonical company (PART B).

The orchestration (``canonicalize_extracted``) is store-agnostic and is tested
with in-memory stores. The DB adapters below wire the same logic to the
``government_events`` / ``event_sources`` / ``companies`` / ``company_aliases``
tables.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.dedup.fingerprint import EventFingerprint
from app.dedup.service import DedupDecision, EventDeduplicator
from app.extraction.mapping import _primary_awardee, strong_identifiers
from app.extraction.schema import EntityRef, ExtractedEvent
from app.resolution.matcher import CompanyObservation
from app.resolution.service import CompanyResolver, ResolutionResult


# --------------------------------------------------------------------------- #
# Converters (ExtractedEvent → dedup/resolution inputs)
# --------------------------------------------------------------------------- #
def fingerprint_from_extracted(event: ExtractedEvent) -> EventFingerprint:
    return EventFingerprint.build(
        identifiers=strong_identifiers(event),
        buyer=event.government_entity,
        company=_primary_awardee(event),
        value=event.contract_value,
        event_date=event.award_date,
        event_type=event.event_type,
        text=event.project or event.description or None,
    )


def primary_awardee_entity(event: ExtractedEvent) -> EntityRef | None:
    for entity in event.entities:
        if entity.role == "awardee":
            return entity
    return event.entities[0] if event.entities else None


def observation_from_entity(entity: EntityRef, event: ExtractedEvent) -> CompanyObservation:
    return CompanyObservation(
        raw_name=entity.name,
        cin=entity.cin,
        gstin=entity.gstin,
        state=event.location,
    )


# --------------------------------------------------------------------------- #
# Orchestration (store-agnostic)
# --------------------------------------------------------------------------- #
@dataclass
class CanonicalizationReport:
    dedup: list[DedupDecision] = field(default_factory=list)
    resolutions: list[ResolutionResult] = field(default_factory=list)


def canonicalize_extracted(
    events: list[ExtractedEvent],
    *,
    deduplicator: EventDeduplicator,
    resolver: CompanyResolver | None = None,
    context: Any = None,
) -> CanonicalizationReport:
    report = CanonicalizationReport()

    items = [(fingerprint_from_extracted(e), e) for e in events]
    report.dedup = deduplicator.process(items, context=context)

    if resolver is not None:
        for event in events:
            entity = primary_awardee_entity(event)
            if entity is None:
                continue
            obs = observation_from_entity(entity, event)
            report.resolutions.append(resolver.resolve(obs, evidence={"event_type": event.event_type}))

    return report
