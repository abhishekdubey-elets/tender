"""Government sources and the raw documents harvested from them.

This is the *authoritative provenance layer*. Nothing here is derived: a
:class:`RawDocument` is a byte-for-byte record of what a government portal
served, and its ``source_url`` is mandatory and never overwritten. Everything
downstream (events, opportunities, briefs) must be traceable back to a row in
this layer.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003  (needed at runtime for Mapped[] resolution)
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import (
    AccessMethod,
    ExtractionStatus,
    GovSourceType,
    Jurisdiction,
    ParseStatus,
)

if TYPE_CHECKING:
    from app.db.models.events import EventSource


class GovernmentSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "government_sources"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[GovSourceType] = mapped_column(
        SAEnum(GovSourceType, name="gov_source_type"), nullable=False
    )
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    access_method: Mapped[AccessMethod] = mapped_column(
        SAEnum(AccessMethod, name="access_method"), nullable=False
    )
    jurisdiction: Mapped[Jurisdiction] = mapped_column(
        SAEnum(Jurisdiction, name="jurisdiction"),
        nullable=False,
        server_default=Jurisdiction.national.value,
    )
    state: Mapped[str | None] = mapped_column(String(120))
    crawl_frequency_minutes: Mapped[int | None] = mapped_column(Integer)
    last_crawled_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Per-source scraper configuration (selectors, endpoints, headers, ...).
    config: Mapped[dict | None] = mapped_column(JSONB)

    raw_documents: Mapped[list["RawDocument"]] = relationship(back_populates="government_source")

    __table_args__ = (UniqueConstraint("slug", name="uq_government_sources_slug"),)


class RawDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "raw_documents"

    government_source_id: Mapped[uuid.UUID] = mapped_column(
        # RESTRICT: never lose provenance by deleting a source out from under
        # its documents.
        ForeignKey("government_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # --- Authoritative provenance (never derived, never overwritten) ---
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha-256 hex
    fetched_at: Mapped["datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    http_status: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    language: Mapped[str | None] = mapped_column(String(16))
    title: Mapped[str | None] = mapped_column(Text)

    # Where the bytes live. Small payloads may sit inline; large blobs go to
    # object storage and are referenced by ``storage_path``.
    storage_backend: Mapped[str | None] = mapped_column(String(32))
    storage_path: Mapped[str | None] = mapped_column(Text)
    raw_content: Mapped[str | None] = mapped_column(Text)

    # --- Derived-but-attributed processing state ---
    parsed_text: Mapped[str | None] = mapped_column(Text)
    parse_status: Mapped[ParseStatus] = mapped_column(
        SAEnum(ParseStatus, name="parse_status"),
        nullable=False,
        server_default=ParseStatus.pending.value,
    )
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        SAEnum(ExtractionStatus, name="extraction_status"),
        nullable=False,
        server_default=ExtractionStatus.pending.value,
    )
    meta: Mapped[dict | None] = mapped_column(JSONB)

    government_source: Mapped["GovernmentSource"] = relationship(back_populates="raw_documents")
    event_sources: Mapped[list["EventSource"]] = relationship(back_populates="raw_document")

    __table_args__ = (
        # A document is uniquely identified within a source by its content
        # hash — re-crawls of unchanged pages are idempotent.
        UniqueConstraint(
            "government_source_id", "content_hash", name="uq_raw_documents_government_source_id_content_hash"
        ),
        Index("ix_raw_documents_source_url", "source_url"),
        Index("ix_raw_documents_government_source_id_fetched_at", "government_source_id", "fetched_at"),
        Index("ix_raw_documents_parse_status", "parse_status"),
        Index("ix_raw_documents_extraction_status", "extraction_status"),
    )
