"""Opportunities and the sales artefacts derived from them.

An :class:`Opportunity` ties a government event + company to a specific tenant
:class:`Organization` (and, optionally, the product/sector that makes it
relevant) — this is the "why is this a sales opening for *me*" record. One event
can spawn many opportunities (different orgs, products, or angles).

:class:`OpportunityEvidence` keeps every opportunity traceable back to the
provenance that justifies it. :class:`LeadScore` and :class:`SalesBrief` are
clearly-derived, versioned artefacts.
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
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import (
    BriefFormat,
    BriefStatus,
    DetectionMethod,
    EvidenceType,
    OpportunityStatus,
    OpportunityType,
    ScoreGrade,
)

if TYPE_CHECKING:
    from app.db.models.companies import Company, Contact
    from app.db.models.crm import Outreach, SalesFeedback
    from app.db.models.events import EventSource, GovernmentEvent
    from app.db.models.sources import RawDocument
    from app.db.models.tenancy import Organization, Product, TargetSector, User


class Opportunity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "opportunities"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    government_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("government_events.id", ondelete="RESTRICT"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    # Which of the org's products/sectors this opportunity is about (optional).
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL")
    )
    target_sector_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("target_sectors.id", ondelete="SET NULL")
    )
    # CRM assignment.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    opportunity_type: Mapped[OpportunityType] = mapped_column(
        SAEnum(OpportunityType, name="opportunity_type"),
        nullable=False,
        server_default=OpportunityType.other.value,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Human/LLM-readable "why this matters". Derived — always backed by evidence.
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[OpportunityStatus] = mapped_column(
        SAEnum(OpportunityStatus, name="opportunity_status"),
        nullable=False,
        server_default=OpportunityStatus.new.value,
    )
    detected_by: Mapped[DetectionMethod] = mapped_column(
        SAEnum(DetectionMethod, name="detection_method"),
        nullable=False,
        server_default=DetectionMethod.rule.value,
    )
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    external_crm_id: Mapped[str | None] = mapped_column(String(255))

    organization: Mapped["Organization"] = relationship(back_populates="opportunities")
    event: Mapped["GovernmentEvent"] = relationship(back_populates="opportunities")
    company: Mapped["Company"] = relationship()
    product: Mapped["Product | None"] = relationship()
    target_sector: Mapped["TargetSector | None"] = relationship()
    owner: Mapped["User | None"] = relationship()

    evidence: Mapped[list["OpportunityEvidence"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    lead_scores: Mapped[list["LeadScore"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    briefs: Mapped[list["SalesBrief"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    outreach: Mapped[list["Outreach"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    feedback: Mapped[list["SalesFeedback"]] = relationship(back_populates="opportunity")

    __table_args__ = (
        # Prevent exact-duplicate opportunities while still allowing many
        # opportunities per event (differing org / company / product / type).
        UniqueConstraint(
            "organization_id", "government_event_id", "company_id", "product_id", "opportunity_type",
            name="uq_opportunities_org_event_company_product_type",
        ),
        Index("ix_opportunities_organization_id_status", "organization_id", "status"),
        Index("ix_opportunities_government_event_id", "government_event_id"),
        Index("ix_opportunities_company_id", "company_id"),
        Index("ix_opportunities_owner_user_id", "owner_user_id"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )


class OpportunityEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_evidence"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    evidence_type: Mapped[EvidenceType] = mapped_column(
        SAEnum(EvidenceType, name="evidence_type"), nullable=False
    )
    # Optional pointers to the concrete provenance backing this opportunity.
    event_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event_sources.id", ondelete="SET NULL")
    )
    raw_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("raw_documents.id", ondelete="SET NULL")
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[float | None] = mapped_column(Numeric(4, 3))

    opportunity: Mapped["Opportunity"] = relationship(back_populates="evidence")
    event_source: Mapped["EventSource | None"] = relationship()
    raw_document: Mapped["RawDocument | None"] = relationship()

    __table_args__ = (
        Index("ix_opportunity_evidence_opportunity_id", "opportunity_id"),
        CheckConstraint("weight >= 0 AND weight <= 1", name="weight_range"),
    )


class LeadScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_scores"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    grade: Mapped[ScoreGrade | None] = mapped_column(SAEnum(ScoreGrade, name="score_grade"))
    # Transparent, per-factor breakdown so scoring is explainable and tunable.
    factors: Mapped[dict | None] = mapped_column(JSONB)
    model_version: Mapped[str | None] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    scored_at: Mapped["datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    opportunity: Mapped["Opportunity"] = relationship(back_populates="lead_scores")

    __table_args__ = (
        Index(
            "uq_lead_scores_opportunity_id_current",
            "opportunity_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index("ix_lead_scores_opportunity_id", "opportunity_id"),
        CheckConstraint("score >= 0", name="score_non_negative"),
    )


class SalesBrief(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_briefs"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL")
    )
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[BriefFormat] = mapped_column(
        SAEnum(BriefFormat, name="brief_format"),
        nullable=False,
        server_default=BriefFormat.markdown.value,
    )
    status: Mapped[BriefStatus] = mapped_column(
        SAEnum(BriefStatus, name="brief_status"),
        nullable=False,
        server_default=BriefStatus.draft.value,
    )
    model: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped["datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    opportunity: Mapped["Opportunity"] = relationship(back_populates="briefs")
    contact: Mapped["Contact | None"] = relationship()

    __table_args__ = (Index("ix_sales_briefs_opportunity_id", "opportunity_id"),)
