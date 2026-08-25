"""Government Event Extraction service.

Turns a normalized government document into validated, structured government
events using an LLM with strict schema validation. The LLM client is injected,
so the service is fully testable with a scripted fake (no API key / network).

Guarantees:
  * strict Pydantic schema validation of the model output;
  * missing fields are ``null``/``unknown`` — never invented;
  * evidence snippets are grounded (must appear verbatim in the source);
  * the model/provider/prompt version and timestamps are recorded;
  * reproducible where possible (stable versioned prompt + input-hash cache);
  * retries on transport errors, schema-validation failures and ungrounded
    evidence.
"""
from __future__ import annotations

from app.extraction.schema import (
    EntityRef,
    Evidence,
    EventExtractionEnvelope,
    ExtractedEvent,
    ExtractionEventType,
)
from app.extraction.service import EventExtractionService
from app.extraction.types import ExtractionResult, ExtractionRunMeta, ExtractionStatus

__all__ = [
    "EventExtractionService",
    "ExtractionResult",
    "ExtractionRunMeta",
    "ExtractionStatus",
    "EventExtractionEnvelope",
    "ExtractedEvent",
    "EntityRef",
    "Evidence",
    "ExtractionEventType",
]
