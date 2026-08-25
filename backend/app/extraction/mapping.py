"""Map validated extraction output onto the database schema.

Each ``ExtractedEvent`` becomes a ``government_events`` row plus an
``event_sources`` evidence row that pins it to the originating ``raw_documents``
record (URL, snippet, the exact extracted payload, confidence and model). The
raw extraction event-type is preserved in ``attributes`` even though it is mapped
onto the coarser DB enum.

``to_orm`` is pure (no session) so the mapping is unit-testable without a DB.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.db.enums import EventType, ExtractionStatus as DbExtractionStatus
from app.db.models import EventSource, GovernmentEvent, RawDocument
from app.extraction.schema import ExtractedEvent
from app.extraction.types import ExtractionResult, ExtractionStatus

# Extraction event types → coarser DB EventType (raw value kept in attributes).
EVENT_TYPE_MAP = {
    "tender": EventType.tender,
    "contract_award": EventType.award,
    "work_order": EventType.work_order,
    "funding": EventType.funding,
    "policy": EventType.policy,
    "scheme": EventType.other,
    "approval": EventType.approval,
    "expansion": EventType.other,
    "other": EventType.other,
}


def map_event_type(value: str) -> EventType:
    return EVENT_TYPE_MAP.get(value, EventType.other)


def normalize_currency(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().upper()
    if "INR" in v or "RUPEE" in v or v in {"RS", "RS.", "₹"}:
        return "INR"
    if "USD" in v or v == "$":
        return "USD"
    return v[:3]


def _primary_awardee(event: ExtractedEvent) -> str | None:
    for entity in event.entities:
        if entity.role == "awardee":
            return entity.name
    return event.entities[0].name if event.entities else None


def strong_identifiers(event: ExtractedEvent) -> list[str]:
    """Non-null strong identifiers in priority order (for dedup)."""
    ids = event.identifiers
    values = [
        ids.tender_number, ids.contract_number, ids.work_order_number,
        ids.project_id, ids.reference_number,
    ]
    return [v for v in values if v]


def compute_dedup_key(event: ExtractedEvent) -> str:
    awardee = (_primary_awardee(event) or "").strip().lower()
    parts = [
        str(event.event_type),
        awardee,
        f"{event.contract_value:.2f}" if event.contract_value is not None else "",
        event.award_date.isoformat() if event.award_date else "",
        (event.government_entity or "").strip().lower(),
        (event.project or "").strip().lower(),
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _to_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def build_government_event(event: ExtractedEvent) -> GovernmentEvent:
    title = event.project or (event.description[:200] if event.description else None) or f"{event.event_type} event"
    ids = strong_identifiers(event)
    return GovernmentEvent(
        event_type=map_event_type(event.event_type),
        title=title,
        summary=event.description,
        buyer_name=event.government_entity,
        awardee_name=_primary_awardee(event),
        value_amount=_to_decimal(event.contract_value),
        currency=normalize_currency(event.currency),
        reference_number=(ids[0][:255] if ids else None),
        event_date=event.award_date,
        published_date=event.announcement_date,
        state=(event.location[:120] if event.location else None),
        confidence=event.confidence,
        dedup_key=compute_dedup_key(event),
        attributes={
            "extraction_event_type": event.event_type,
            "sector": event.sector,
            "location": event.location,
            "project": event.project,
            "government_entity": event.government_entity,
            "identifiers": event.identifiers.model_dump(mode="json"),
            "entities": [e.model_dump(mode="json") for e in event.entities],
        },
    )


def build_event_source(
    event: ExtractedEvent, government_event: GovernmentEvent, raw_document: RawDocument, model: str
) -> EventSource:
    snippet = "\n".join(e.snippet for e in event.evidence) or None
    es = EventSource(
        raw_document_id=raw_document.id,
        government_source_id=raw_document.government_source_id,
        source_url=raw_document.source_url,
        snippet=snippet,
        extracted_payload=event.model_dump(mode="json"),
        confidence=event.confidence,
        extraction_model=model,
        is_primary=True,
    )
    es.event = government_event
    return es


def to_orm(
    result: ExtractionResult, raw_document: RawDocument
) -> list[tuple[GovernmentEvent, EventSource]]:
    pairs: list[tuple[GovernmentEvent, EventSource]] = []
    for event in result.events:
        ge = build_government_event(event)
        es = build_event_source(event, ge, raw_document, result.meta.model)
        pairs.append((ge, es))
    return pairs


def persist_events(
    session: Session, raw_document: RawDocument, result: ExtractionResult
) -> list[GovernmentEvent]:
    events: list[GovernmentEvent] = []
    for ge, es in to_orm(result, raw_document):
        session.add(ge)
        session.add(es)
        events.append(ge)

    if result.status is ExtractionStatus.succeeded:
        raw_document.extraction_status = DbExtractionStatus.extracted
    elif result.status is ExtractionStatus.skipped:
        raw_document.extraction_status = DbExtractionStatus.skipped
    else:
        raw_document.extraction_status = DbExtractionStatus.failed

    session.flush()
    return events
