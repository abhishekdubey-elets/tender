"""API response/request models (mirror the dashboard's data shape)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.feedback.types import FeedbackEventType


class EventOut(BaseModel):
    type: str
    type_label: str
    title: str
    value: float | None = None
    org: str
    department: str | None = None
    sector: str | None = None
    date: str | None = None
    reference: str | None = None
    location: str | None = None


class ContactOut(BaseModel):
    name: str | None = None
    title: str | None = None
    verified: bool = False
    # email/phone are PII — omitted from list responses, included in detail only
    email: str | None = None
    linkedin: str | None = None
    source: str | None = None
    confidence: float | None = None


class LeadSummary(BaseModel):
    id: str
    company: str
    status: str
    event: EventOut
    opportunity: str
    opportunity_tier: str
    score: int
    grade: str
    confidence: float
    why_now: str
    reason_to_call: str
    target_contact: str            # role or verified name (no raw PII in list)


class EvidenceOut(BaseModel):
    id: str
    tier: str
    statement: str
    snippet: str | None = None
    source_url: str | None = None
    confidence: float | None = None


class ScoreComponentOut(BaseModel):
    key: str
    points: int
    max_points: int
    note: str | None = None


class BriefSectionOut(BaseModel):
    key: str
    title: str
    text: str
    is_inference: bool


class SourceDocOut(BaseModel):
    title: str
    url: str
    kind: str | None = None
    date: str | None = None


class LeadDetail(LeadSummary):
    company_profile: dict
    opportunity_detail: dict
    evidence: list[EvidenceOut]
    score_components: list[ScoreComponentOut]
    contact: ContactOut | None = None
    brief: list[BriefSectionOut]
    risk: str | None = None
    sources: list[SourceDocOut]


class FeedbackIn(BaseModel):
    event_type: FeedbackEventType
    note: str | None = Field(default=None, max_length=2000)


class FeedbackAck(BaseModel):
    lead_id: str
    event_type: FeedbackEventType
    recorded: bool = True
    status: str
