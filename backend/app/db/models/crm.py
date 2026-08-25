"""CRM-facing activity: outreach logs and sales feedback.

These tables make the platform usable as (and syncable with) a CRM. Outreach is
the activity timeline against a contact/opportunity; SalesFeedback captures rep
outcomes that feed the scoring and data-quality feedback loop.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003  (runtime-needed for Mapped[] resolution)
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import (
    FeedbackOutcome,
    OutreachChannel,
    OutreachDirection,
    OutreachStatus,
)

if TYPE_CHECKING:
    from app.db.models.companies import Contact
    from app.db.models.opportunities import LeadScore, Opportunity
    from app.db.models.tenancy import User


class Outreach(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outreach"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="RESTRICT")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    channel: Mapped[OutreachChannel] = mapped_column(
        SAEnum(OutreachChannel, name="outreach_channel"), nullable=False
    )
    direction: Mapped[OutreachDirection] = mapped_column(
        SAEnum(OutreachDirection, name="outreach_direction"),
        nullable=False,
        server_default=OutreachDirection.outbound.value,
    )
    status: Mapped[OutreachStatus] = mapped_column(
        SAEnum(OutreachStatus, name="outreach_status"),
        nullable=False,
        server_default=OutreachStatus.planned.value,
    )
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True))
    external_crm_id: Mapped[str | None] = mapped_column(String(255))
    meta: Mapped[dict | None] = mapped_column(JSONB)

    opportunity: Mapped["Opportunity"] = relationship(back_populates="outreach")
    contact: Mapped["Contact | None"] = relationship()
    user: Mapped["User | None"] = relationship()

    __table_args__ = (
        Index("ix_outreach_opportunity_id", "opportunity_id"),
        Index("ix_outreach_contact_id", "contact_id"),
        Index("ix_outreach_user_id", "user_id"),
        Index("ix_outreach_occurred_at", "occurred_at"),
    )


class SalesFeedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_feedback"

    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE")
    )
    outreach_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outreach.id", ondelete="SET NULL")
    )
    lead_score_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lead_scores.id", ondelete="SET NULL")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    outcome: Mapped[FeedbackOutcome] = mapped_column(
        SAEnum(FeedbackOutcome, name="feedback_outcome"), nullable=False
    )
    rating: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    # Raised when the rep reports the underlying data was wrong — routes back to
    # extraction / resolution quality queues.
    data_quality_flag: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("false")
    )

    opportunity: Mapped["Opportunity | None"] = relationship(back_populates="feedback")
    lead_score: Mapped["LeadScore | None"] = relationship()
    user: Mapped["User | None"] = relationship()

    __table_args__ = (
        Index("ix_sales_feedback_opportunity_id", "opportunity_id"),
        Index("ix_sales_feedback_user_id", "user_id"),
    )
