"""Government events (canonical) and their per-source evidence.

A :class:`GovernmentEvent` is *derived* — the deduplicated, consolidated view
of a real-world happening (a tender, an award, a funding release, ...). It is
never the source of truth on its own: every event is backed by one or more
:class:`EventSource` rows, each of which pins the exact document, URL, snippet
and extraction confidence that evidenced it. Multiple sources reporting the
same event therefore produce one event and several evidence rows.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime  # noqa: TC003  (runtime-needed for Mapped[] resolution)
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import EventStatus, EventType, Jurisdiction

if TYPE_CHECKING:
    from app.db.models.companies import Company
    from app.db.models.opportunities import Opportunity
    from app.db.models.sources import GovernmentSource, RawDocument

# pgvector column type. Embeddings power semantic dedup / company matching.
try:  # pragma: no cover - import guard for environments without pgvector
    from pgvector.sqlalchemy import Vector

    _EMBEDDING_DIM = 1024  # e.g. voyage-3 / bge-large
    _embedding_type = Vector(_EMBEDDING_DIM)
except ImportError:  # pragma: no cover
    _embedding_type = None


class GovernmentEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "government_events"

    event_type: Mapped[EventType] = mapped_column(
        SAEnum(EventType, name="event_type"), nullable=False
    )
    status: Mapped[EventStatus] = mapped_column(
        SAEnum(EventStatus, name="event_status"),
        nullable=False,
        server_default=EventStatus.active.value,
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)

    # Government side of the transaction.
    buyer_name: Mapped[str | None] = mapped_column(Text)
    buyer_department: Mapped[str | None] = mapped_column(Text)

    # Awardee/recipient side, as consolidated. The *raw* awardee string per
    # source lives on EventSource; this is the resolver's best canonical guess.
    awardee_name: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        # SET NULL: resolving/unresolving a company must never delete the event.
        ForeignKey("companies.id", ondelete="SET NULL")
    )
    company_resolution_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))

    # Monetary value. ``value_amount`` is as-reported in its native currency;
    # ``value_amount_inr`` is a DERIVED normalisation kept separate and clearly
    # named so it is never mistaken for the source figure.
    value_amount: Mapped[float | None] = mapped_column(Numeric(20, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    value_amount_inr: Mapped[float | None] = mapped_column(Numeric(20, 2))

    reference_number: Mapped[str | None] = mapped_column(String(255))
    jurisdiction: Mapped[Jurisdiction | None] = mapped_column(
        SAEnum(Jurisdiction, name="jurisdiction")
    )
    state: Mapped[str | None] = mapped_column(String(120))

    event_date: Mapped["date | None"] = mapped_column(Date)
    published_date: Mapped["date | None"] = mapped_column(Date)

    # Deduplication key (normalised composite of ref-no/awardee/value/date).
    dedup_key: Mapped[str | None] = mapped_column(String(255))
    # Overall extraction/consolidation confidence for the canonical record.
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))

    first_seen_at: Mapped["datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_seen_at: Mapped["datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    attributes: Mapped[dict | None] = mapped_column(JSONB)

    if _embedding_type is not None:
        embedding: Mapped[list[float] | None] = mapped_column(_embedding_type)

    company: Mapped["Company | None"] = relationship(back_populates="events")
    sources: Mapped[list["EventSource"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="event")

    __table_args__ = (
        # dedup_key is unique when present (NULLs allowed while unresolved).
        Index("uq_government_events_dedup_key", "dedup_key", unique=True, postgresql_where=text("dedup_key IS NOT NULL")),
        Index("ix_government_events_event_type", "event_type"),
        Index("ix_government_events_status", "status"),
        Index("ix_government_events_event_date", "event_date"),
        Index("ix_government_events_company_id", "company_id"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(
            "company_resolution_confidence >= 0 AND company_resolution_confidence <= 1",
            name="resolution_confidence_range",
        ),
        CheckConstraint("value_amount >= 0", name="value_amount_non_negative"),
    )


class EventSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Evidence linking one government event to one raw document.

    This join carries the authoritative, per-source facts: the exact URL and
    text snippet that support the event, plus the extraction confidence and the
    model that produced it. It is what lets several sources back a single event
    without collapsing their individual provenance.
    """

    __tablename__ = "event_sources"

    government_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("government_events.id", ondelete="CASCADE"), nullable=False
    )
    raw_document_id: Mapped[uuid.UUID] = mapped_column(
        # RESTRICT: the original document is the ground truth — never cascade it
        # away.
        ForeignKey("raw_documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    government_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("government_sources.id", ondelete="RESTRICT"), nullable=False
    )

    # Snapshot of the URL that evidenced this event (never lost, even if the
    # raw document is later re-located in storage).
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text)
    # The structured payload this specific source yielded for the event.
    extracted_payload: Mapped[dict | None] = mapped_column(JSONB)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    extraction_model: Mapped[str | None] = mapped_column(String(120))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    event: Mapped["GovernmentEvent"] = relationship(back_populates="sources")
    raw_document: Mapped["RawDocument"] = relationship(back_populates="event_sources")
    government_source: Mapped["GovernmentSource"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "government_event_id", "raw_document_id",
            name="uq_event_sources_government_event_id_raw_document_id",
        ),
        Index("ix_event_sources_government_event_id", "government_event_id"),
        Index("ix_event_sources_raw_document_id", "raw_document_id"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )
