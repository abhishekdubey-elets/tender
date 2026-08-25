"""Strict Pydantic schema for extracted government events.

This schema is both (a) the JSON schema handed to the LLM for structured output
and (b) the validator applied to the model's response. ``extra="forbid"`` makes
the model unable to add unknown keys, and every business field is optional and
defaults to ``None`` so *missing → null* is the enforced default (the model is
instructed never to guess).
"""
from __future__ import annotations

import enum
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ExtractionEventType(str, enum.Enum):
    tender = "tender"
    contract_award = "contract_award"
    work_order = "work_order"
    funding = "funding"
    policy = "policy"
    scheme = "scheme"
    approval = "approval"
    expansion = "expansion"
    other = "other"


class EntityRole(str, enum.Enum):
    awardee = "awardee"
    bidder = "bidder"
    implementing_agency = "implementing_agency"
    vendor = "vendor"
    partner = "partner"
    beneficiary = "beneficiary"
    other = "other"
    unknown = "unknown"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class EntityRef(_Strict):
    name: str = Field(description="Company/organisation name exactly as written in the document")
    role: EntityRole = Field(default=EntityRole.unknown)
    cin: str | None = Field(default=None, description="Corporate Identity Number if explicitly stated")
    gstin: str | None = Field(default=None)


class Evidence(_Strict):
    field: str = Field(description="Which claim this supports, e.g. 'contract_value' or 'entities[0].name'")
    snippet: str = Field(description="Text copied VERBATIM from the document supporting the claim")


class EventIdentifiers(_Strict):
    """Strong identifiers used for deterministic deduplication. All optional."""

    tender_number: str | None = Field(default=None)
    contract_number: str | None = Field(default=None)
    work_order_number: str | None = Field(default=None)
    project_id: str | None = Field(default=None)
    reference_number: str | None = Field(default=None)


class ExtractedEvent(_Strict):
    event_type: ExtractionEventType
    identifiers: EventIdentifiers = Field(default_factory=EventIdentifiers)
    government_entity: str | None = Field(
        default=None, description="Government body/ministry/department involved"
    )
    entities: list[EntityRef] = Field(
        default_factory=list, description="Companies/organisations involved (may be empty)"
    )
    contract_value: float | None = Field(default=None, description="Numeric value; null if not stated")
    currency: str | None = Field(default=None, description="ISO code or symbol as stated, e.g. 'INR'")
    sector: str | None = Field(default=None)
    project: str | None = Field(default=None, description="Project/scheme/programme name")
    award_date: date | None = Field(default=None, description="Award/tender date (ISO); null if unknown")
    announcement_date: date | None = Field(default=None)
    location: str | None = Field(default=None, description="State/city/region as stated")
    description: str | None = Field(default=None, description="One or two sentence factual summary")
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, description="Model's confidence in THIS event (0..1)")


class EventExtractionEnvelope(_Strict):
    """Top-level LLM output. A single document may yield zero or many events."""

    events: list[ExtractedEvent] = Field(default_factory=list)
    document_summary: str | None = Field(default=None)


def envelope_json_schema() -> dict:
    """JSON schema handed to the LLM's structured-output config."""
    return EventExtractionEnvelope.model_json_schema()
