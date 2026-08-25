"""Append-only feedback event store.

Immutability is structural: events are frozen dataclasses, and the store exposes
only append + read — never update or delete. This is what makes the feedback
dataset a reliable, audit-safe record.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.feedback.types import FeedbackEvent


@runtime_checkable
class FeedbackStore(Protocol):
    def append(self, event: FeedbackEvent) -> FeedbackEvent: ...

    def events(self) -> list[FeedbackEvent]: ...

    def for_lead(self, lead_id: Any) -> list[FeedbackEvent]: ...


class InMemoryFeedbackStore:
    def __init__(self) -> None:
        self._events: list[FeedbackEvent] = []

    def append(self, event: FeedbackEvent) -> FeedbackEvent:
        self._events.append(event)
        return event

    def events(self) -> list[FeedbackEvent]:
        # Return a copy so callers cannot mutate the log.
        return list(self._events)

    def for_lead(self, lead_id: Any) -> list[FeedbackEvent]:
        return [e for e in self._events if e.lead_id == lead_id]

    def __len__(self) -> int:
        return len(self._events)
