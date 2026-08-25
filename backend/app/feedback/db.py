"""Persist feedback as immutable rows in ``sales_feedback`` (append-only).

The granular event type is preserved in ``notes`` (prefixed) and mapped onto the
schema's coarser ``FeedbackOutcome`` enum; incorrect-* events set
``data_quality_flag`` so they route back to extraction/resolution quality.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.enums import FeedbackOutcome
from app.db.models import SalesFeedback as SalesFeedbackRow
from app.feedback.types import DATA_QUALITY_EVENTS, FeedbackEventType

_OUTCOME_MAP = {
    FeedbackEventType.lead_viewed: FeedbackOutcome.neutral,
    FeedbackEventType.lead_accepted: FeedbackOutcome.positive,
    FeedbackEventType.contacted: FeedbackOutcome.neutral,
    FeedbackEventType.meeting_booked: FeedbackOutcome.positive,
    FeedbackEventType.opportunity_created: FeedbackOutcome.converted,
    FeedbackEventType.lead_rejected: FeedbackOutcome.negative,
    FeedbackEventType.not_relevant: FeedbackOutcome.not_interested,
    FeedbackEventType.incorrect_company: FeedbackOutcome.bad_data,
    FeedbackEventType.incorrect_opportunity: FeedbackOutcome.bad_data,
    FeedbackEventType.incorrect_contact: FeedbackOutcome.wrong_contact,
}


def record_feedback(
    session: Session,
    *,
    event_type: FeedbackEventType,
    opportunity_id: Any | None = None,
    user_id: Any | None = None,
    note: str | None = None,
    lead_score_id: Any | None = None,
    outreach_id: Any | None = None,
    rating: int | None = None,
) -> SalesFeedbackRow:
    row = SalesFeedbackRow(
        opportunity_id=opportunity_id,
        outreach_id=outreach_id,
        lead_score_id=lead_score_id,
        user_id=user_id,
        outcome=_OUTCOME_MAP[event_type],
        rating=rating,
        notes=f"[{event_type.value}] {note or ''}".strip(),
        data_quality_flag=event_type in DATA_QUALITY_EVENTS,
    )
    session.add(row)          # append only — feedback rows are never updated
    session.flush()
    return row
