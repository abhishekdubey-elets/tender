"""Operational tables: pipeline job tracking and the audit trail.

:class:`ProcessingJob` records every unit of pipeline work (crawl, parse,
extract, ...) with status, retries and error context, so the pipeline is
observable and re-runnable. :class:`AuditLog` is an append-only trail of
who/what changed which entity — important for a system that mutates
opportunity state and merges company records.
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
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import ActorType, JobStatus, JobType

if TYPE_CHECKING:
    from app.db.models.tenancy import User


class ProcessingJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "processing_jobs"

    job_type: Mapped[JobType] = mapped_column(SAEnum(JobType, name="job_type"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status"),
        nullable=False,
        server_default=JobStatus.pending.value,
    )

    # Optional links to what the job operates on. Kept as loose references
    # (target_table/target_id) so a job can point at any pipeline entity.
    government_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("government_sources.id", ondelete="SET NULL")
    )
    raw_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("raw_documents.id", ondelete="SET NULL")
    )
    target_table: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[uuid.UUID | None] = mapped_column()

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    scheduled_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True))
    started_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_processing_jobs_status_job_type", "status", "job_type"),
        Index("ix_processing_jobs_scheduled_at", "scheduled_at"),
        Index("ix_processing_jobs_raw_document_id", "raw_document_id"),
    )


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Append-only. No ``updated_at`` — rows are never mutated."""

    __tablename__ = "audit_logs"

    created_at: Mapped["datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    actor_type: Mapped[ActorType] = mapped_column(
        SAEnum(ActorType, name="actor_type"),
        nullable=False,
        server_default=ActorType.system.value,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False)  # e.g. "opportunity.status_change"
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    meta: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)

    actor_user: Mapped["User | None"] = relationship()

    __table_args__ = (
        Index("ix_audit_logs_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_logs_actor_user_id", "actor_user_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )
