"""Integration with the database schema.

Processing enriches a ``raw_documents`` row that ingestion already created:
normalized text → ``parsed_text``, status → ``parse_status``, and the extraction
method/confidence/classification/metadata/hashes → ``meta`` (JSONB). Each
processing attempt is recorded as a ``processing_jobs`` row, which is what makes
processing **retryable** and gives **failure tracking**.

``apply_outcome_fields`` is a pure function (no session) so the field mapping is
unit-testable without a live database.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import JobStatus, JobType, ParseStatus
from app.db.models import ProcessingJob, RawDocument
from app.processing.types import ProcessingOutcome, ProcessingStatus, SourceFile

_STATUS_TO_PARSE = {
    ProcessingStatus.succeeded: ParseStatus.parsed,
    ProcessingStatus.failed: ParseStatus.failed,
    ProcessingStatus.needs_ocr: ParseStatus.skipped,   # deferred until OCR runs
}

_STATUS_TO_JOB = {
    ProcessingStatus.succeeded: JobStatus.succeeded,
    ProcessingStatus.failed: JobStatus.failed,
    ProcessingStatus.needs_ocr: JobStatus.retrying,
}


def build_processing_meta(outcome: ProcessingOutcome) -> dict:
    """The JSONB blob written under ``raw_documents.meta['processing']`` etc."""
    processing = {
        "status": outcome.status.value,
        "error": outcome.error,
        "error_kind": outcome.error_kind,
        "duplicate_of": outcome.duplicate_of,
        "warnings": outcome.warnings or None,
    }
    result: dict = {"processing": {k: v for k, v in processing.items() if v is not None}}

    norm = outcome.normalized
    if norm is not None:
        result["processing"].update(
            {
                "doc_class": norm.doc_class.value,
                "extraction_method": norm.extraction_method,
                "extraction_confidence": (
                    float(norm.extraction_confidence)
                    if norm.extraction_confidence is not None
                    else None
                ),
                "ocr_used": norm.ocr_used,
                "detected_mime": norm.detected_mime,
            }
        )
        result["hashes"] = {"sha256": norm.sha256, "md5": norm.md5, "byte_size": norm.byte_size}
        md = norm.metadata
        result["document_metadata"] = {
            k: v
            for k, v in {
                "title": md.title,
                "author": md.author,
                "created": md.created,
                "modified": md.modified,
                "page_count": md.page_count,
                "sheet_names": md.sheet_names,
                "language": md.language,
            }.items()
            if v is not None
        }
    elif outcome.sha256:
        result["hashes"] = {"sha256": outcome.sha256}
    return result


def apply_outcome_fields(raw_document: RawDocument, outcome: ProcessingOutcome) -> None:
    """Mutate a RawDocument in place from a processing outcome (no DB access)."""
    raw_document.parse_status = _STATUS_TO_PARSE[outcome.status]
    norm = outcome.normalized
    if norm is not None:
        raw_document.parsed_text = norm.text
        if norm.detected_mime:
            raw_document.mime_type = norm.detected_mime
        if norm.metadata.title and not raw_document.title:
            raw_document.title = norm.metadata.title
        if norm.metadata.language:
            raw_document.language = norm.metadata.language

    # Merge processing metadata into existing meta (preserve anything already set).
    meta = dict(raw_document.meta or {})
    meta.update(build_processing_meta(outcome))
    raw_document.meta = meta


def find_duplicate(
    session: Session, content_hash: str, *, exclude_id: uuid.UUID | None = None
) -> uuid.UUID | None:
    """Return the id of an existing raw_document with the same content hash."""
    stmt = select(RawDocument.id).where(RawDocument.content_hash == content_hash)
    if exclude_id is not None:
        stmt = stmt.where(RawDocument.id != exclude_id)
    return session.scalar(stmt.limit(1))


def persist_outcome(
    session: Session,
    raw_document: RawDocument,
    outcome: ProcessingOutcome,
    *,
    attempt: int = 1,
) -> ProcessingJob:
    """Apply the outcome to the raw_document, flag duplicates, and record a
    ``processing_jobs`` row for this attempt. Returns the job."""
    # Exact-duplicate detection against other stored documents.
    if outcome.sha256 and outcome.duplicate_of is None:
        dup = find_duplicate(session, outcome.sha256, exclude_id=raw_document.id)
        if dup is not None:
            outcome.duplicate_of = str(dup)
            outcome.warnings = [*outcome.warnings, f"duplicate_of:{dup}"]

    apply_outcome_fields(raw_document, outcome)

    job = ProcessingJob(
        job_type=JobType.parse,
        status=_STATUS_TO_JOB[outcome.status],
        raw_document_id=raw_document.id,
        target_table="raw_documents",
        target_id=raw_document.id,
        attempts=attempt,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        error=outcome.error,
        result=build_processing_meta(outcome),
    )
    session.add(job)
    session.flush()
    return job


def load_source_file(raw_document: RawDocument, *, content: bytes | None = None) -> SourceFile:
    """Build a SourceFile from a stored raw_document.

    ``content`` may be supplied directly; otherwise the inline ``raw_content`` is
    used (binary payloads kept only on disk must have their bytes passed in).
    """
    if content is None:
        if raw_document.raw_content is not None:
            content = raw_document.raw_content.encode("utf-8")
        else:
            raise ValueError("raw_document has no inline content; pass bytes via `content`")
    source_name = raw_document.government_source.name if raw_document.government_source else "unknown"
    source_type = (
        raw_document.government_source.source_type.value
        if raw_document.government_source
        else "unknown"
    )
    return SourceFile(
        content=content,
        source_url=raw_document.source_url,
        source_name=source_name,
        source_type=source_type,
        fetched_at=raw_document.fetched_at,
        declared_mime=raw_document.mime_type,
        filename=None,
    )


def retryable_jobs(session: Session, *, limit: int = 100) -> list[ProcessingJob]:
    """Failed/retrying parse jobs that still have attempts left — the retry queue."""
    stmt = (
        select(ProcessingJob)
        .where(
            ProcessingJob.job_type == JobType.parse,
            ProcessingJob.status.in_([JobStatus.failed, JobStatus.retrying]),
            ProcessingJob.attempts < ProcessingJob.max_attempts,
        )
        .limit(limit)
    )
    return list(session.scalars(stmt))
