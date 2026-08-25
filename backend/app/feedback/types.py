"""Feedback event types, outcome classes, and per-lead reduction types."""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class FeedbackEventType(str, enum.Enum):
    lead_viewed = "lead_viewed"
    lead_accepted = "lead_accepted"
    lead_rejected = "lead_rejected"
    contacted = "contacted"
    meeting_booked = "meeting_booked"
    opportunity_created = "opportunity_created"
    not_relevant = "not_relevant"
    incorrect_company = "incorrect_company"
    incorrect_opportunity = "incorrect_opportunity"
    incorrect_contact = "incorrect_contact"


class OutcomeClass(str, enum.Enum):
    view = "view"               # looked at, no decision
    engaged = "engaged"         # accepted / contacted
    converted = "converted"     # meeting booked / opportunity created
    negative = "negative"       # rejected / not relevant
    data_error = "data_error"   # incorrect company/opportunity/contact


EVENT_CLASS = {
    FeedbackEventType.lead_viewed: OutcomeClass.view,
    FeedbackEventType.lead_accepted: OutcomeClass.engaged,
    FeedbackEventType.contacted: OutcomeClass.engaged,
    FeedbackEventType.meeting_booked: OutcomeClass.converted,
    FeedbackEventType.opportunity_created: OutcomeClass.converted,
    FeedbackEventType.lead_rejected: OutcomeClass.negative,
    FeedbackEventType.not_relevant: OutcomeClass.negative,
    FeedbackEventType.incorrect_company: OutcomeClass.data_error,
    FeedbackEventType.incorrect_opportunity: OutcomeClass.data_error,
    FeedbackEventType.incorrect_contact: OutcomeClass.data_error,
}

# Feedback that indicates the underlying data was wrong (routes to data quality).
DATA_QUALITY_EVENTS = {
    FeedbackEventType.incorrect_company,
    FeedbackEventType.incorrect_opportunity,
    FeedbackEventType.incorrect_contact,
}


@dataclass(frozen=True)
class FeedbackEvent:
    """An immutable feedback event. Frozen — never updated or deleted."""

    lead_id: Any
    event_type: FeedbackEventType
    occurred_at: datetime
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    opportunity_id: Any | None = None
    actor_user_id: Any | None = None
    note: str | None = None
    # Score snapshot at feedback time — keeps the label tied to what was shown.
    score_at_event: int | None = None
    config_version: str | None = None
    metadata: dict | None = None

    @property
    def outcome_class(self) -> OutcomeClass:
        return EVENT_CLASS[self.event_type]

    @property
    def is_data_quality(self) -> bool:
        return self.event_type in DATA_QUALITY_EVENTS


@dataclass(slots=True)
class LeadMeta:
    lead_id: Any
    score: int
    grade: str | None = None
    event_type: str | None = None      # government event type
    product: str | None = None
    sector: str | None = None
    company: str | None = None


@dataclass(slots=True)
class LeadOutcome:
    lead_id: Any
    label: OutcomeClass
    converted: bool
    negative: bool
    data_errors: list[str] = field(default_factory=list)
    event_count: int = 0
    converted_via: str | None = None
