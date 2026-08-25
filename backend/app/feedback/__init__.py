"""Sales feedback system.

Captures rep feedback as immutable, append-only events, derives per-lead
outcomes, computes conversion/precision analytics, and provides an evaluation
harness to compare a baseline scoring config against a new one over the collected
feedback — with historical scores kept reproducible. No ML retraining: the goal
here is a reliable feedback dataset + evaluation, not a learned model.
"""
from __future__ import annotations

from app.feedback.analytics import AnalyticsReport, FeedbackAnalytics
from app.feedback.evaluation import (
    EvaluationExample,
    compare_configs,
    evaluate,
    verify_reproducible,
)
from app.feedback.store import InMemoryFeedbackStore
from app.feedback.types import (
    EVENT_CLASS,
    FeedbackEvent,
    FeedbackEventType,
    LeadMeta,
    LeadOutcome,
    OutcomeClass,
)

__all__ = [
    "FeedbackEventType",
    "OutcomeClass",
    "EVENT_CLASS",
    "FeedbackEvent",
    "LeadMeta",
    "LeadOutcome",
    "InMemoryFeedbackStore",
    "FeedbackAnalytics",
    "AnalyticsReport",
    "EvaluationExample",
    "evaluate",
    "compare_configs",
    "verify_reproducible",
]
