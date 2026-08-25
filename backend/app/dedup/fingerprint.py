"""An EventFingerprint captures the normalized, comparable essence of an event.

Built from primitive fields so the dedup layer stays independent of the
extraction/ORM types (converters live in the integration layer).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.dedup.normalize import normalize_identifier, normalize_name


@dataclass(slots=True)
class EventFingerprint:
    identifiers: frozenset[str] = field(default_factory=frozenset)
    buyer: str | None = None
    company: str | None = None
    value: Decimal | None = None
    event_date: date | None = None
    event_type: str | None = None
    text: str | None = None          # title/summary, for semantic comparison

    @classmethod
    def build(
        cls,
        *,
        identifiers: list[str | None] | None = None,
        buyer: str | None = None,
        company: str | None = None,
        value: Decimal | float | None = None,
        event_date: date | None = None,
        event_type: str | None = None,
        text: str | None = None,
    ) -> EventFingerprint:
        norm_ids = frozenset(
            i for i in (normalize_identifier(x) for x in (identifiers or [])) if i
        )
        return cls(
            identifiers=norm_ids,
            buyer=normalize_name(buyer),
            company=normalize_name(company),
            value=Decimal(str(value)) if value is not None else None,
            event_date=event_date,
            event_type=event_type,
            text=text,
        )
