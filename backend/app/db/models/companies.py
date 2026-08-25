"""Companies (the government-money recipients / prospects) and their satellites.

A :class:`Company` is a canonical, resolved entity. The messy strings that map
onto it live in :class:`CompanyAlias`; provider-attributed, time-stamped
enrichment (which is *derived*) lives in :class:`CompanyEnrichment` so it is
never confused with the core record; and decision-makers live in
:class:`Contact`.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003  (runtime-needed for Mapped[] resolution)
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import (
    AliasSource,
    AliasType,
    ContactSource,
    EnrichmentProvider,
    Seniority,
)

if TYPE_CHECKING:
    from app.db.models.events import GovernmentEvent

try:  # pragma: no cover
    from pgvector.sqlalchemy import Vector

    _name_embedding_type = Vector(1024)
except ImportError:  # pragma: no cover
    _name_embedding_type = None


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)  # lowercased/cleaned for matching

    # Indian statutory identifiers (nullable — not always known at resolution).
    cin: Mapped[str | None] = mapped_column(String(21))   # Corporate Identity Number
    gstin: Mapped[str | None] = mapped_column(String(15))
    pan: Mapped[str | None] = mapped_column(String(10))

    website: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String(255))
    sector: Mapped[str | None] = mapped_column(String(255))
    size_band: Mapped[str | None] = mapped_column(String(64))
    hq_state: Mapped[str | None] = mapped_column(String(120))
    hq_city: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2), nullable=False, server_default=text("'IN'"))

    # Whether entity-resolution has been confirmed by a human.
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    if _name_embedding_type is not None:
        name_embedding: Mapped[list[float] | None] = mapped_column(_name_embedding_type)

    aliases: Mapped[list["CompanyAlias"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    enrichments: Mapped[list["CompanyEnrichment"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    events: Mapped[list["GovernmentEvent"]] = relationship(back_populates="company")

    __table_args__ = (
        Index("uq_companies_cin", "cin", unique=True, postgresql_where=text("cin IS NOT NULL")),
        Index("uq_companies_gstin", "gstin", unique=True, postgresql_where=text("gstin IS NOT NULL")),
        Index("ix_companies_normalized_name", "normalized_name"),
        Index("ix_companies_domain", "domain"),
    )


class CompanyAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "company_aliases"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_alias: Mapped[str] = mapped_column(Text, nullable=False)
    alias_type: Mapped[AliasType] = mapped_column(
        SAEnum(AliasType, name="alias_type"),
        nullable=False,
        server_default=AliasType.as_reported.value,
    )
    source: Mapped[AliasSource] = mapped_column(
        SAEnum(AliasSource, name="alias_source"),
        nullable=False,
        server_default=AliasSource.government_event.value,
    )
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))

    company: Mapped["Company"] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint(
            "company_id", "normalized_alias",
            name="uq_company_aliases_company_id_normalized_alias",
        ),
        Index("ix_company_aliases_normalized_alias", "normalized_alias"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )


class CompanyEnrichment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Provider-attributed, versioned enrichment. Explicitly derived data."""

    __tablename__ = "company_enrichment"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[EnrichmentProvider] = mapped_column(
        SAEnum(EnrichmentProvider, name="enrichment_provider"), nullable=False
    )
    # Raw provider payload, kept verbatim for auditability.
    data: Mapped[dict | None] = mapped_column(JSONB)
    employee_count: Mapped[int | None] = mapped_column(Numeric(12, 0))
    annual_revenue: Mapped[float | None] = mapped_column(Numeric(20, 2))
    founded_year: Mapped[int | None] = mapped_column(Numeric(4, 0))
    industry: Mapped[str | None] = mapped_column(String(255))
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    fetched_at: Mapped["datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Exactly one current snapshot per (company, provider).
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship(back_populates="enrichments")

    __table_args__ = (
        Index("ix_company_enrichment_company_id", "company_id"),
        Index(
            "uq_company_enrichment_company_id_provider_current",
            "company_id", "provider",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )


class Contact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contacts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    seniority: Mapped[Seniority] = mapped_column(
        SAEnum(Seniority, name="seniority"),
        nullable=False,
        server_default=Seniority.unknown.value,
    )
    department: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(64))
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[ContactSource] = mapped_column(
        SAEnum(ContactSource, name="contact_source"),
        nullable=False,
        server_default=ContactSource.other.value,
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    # DPDP (India) compliance note: recorded lawful basis for holding this PII.
    lawful_basis: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    do_not_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Stable id in an external CRM once synced (future integration).
    external_crm_id: Mapped[str | None] = mapped_column(String(255))

    company: Mapped["Company"] = relationship(back_populates="contacts")

    __table_args__ = (
        Index("ix_contacts_company_id", "company_id"),
        Index("ix_contacts_linkedin_url", "linkedin_url"),
        Index(
            "uq_contacts_lower_email",
            func.lower(email),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )
