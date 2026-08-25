"""Analytics over the immutable feedback log.

Reduces each lead's event stream to a single outcome, then reports precision of
high-scoring leads, conversion by score bucket / event type / product / sector,
false-positive patterns and false-negative examples.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.feedback.types import FeedbackEvent, LeadMeta, LeadOutcome, OutcomeClass

DEFAULT_BUCKETS = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]


def reduce_lead(lead_id: Any, events: Iterable[FeedbackEvent]) -> LeadOutcome:
    events = list(events)
    classes = [e.outcome_class for e in events]
    data_errors = [e.event_type.value for e in events if e.outcome_class is OutcomeClass.data_error]
    converted_via = next(
        (e.event_type.value for e in events if e.outcome_class is OutcomeClass.converted), None
    )

    if OutcomeClass.converted in classes:
        label, converted, negative = OutcomeClass.converted, True, False
    elif OutcomeClass.negative in classes or OutcomeClass.data_error in classes:
        label, converted, negative = OutcomeClass.negative, False, True
    elif OutcomeClass.engaged in classes:
        label, converted, negative = OutcomeClass.engaged, False, False
    else:
        label, converted, negative = OutcomeClass.view, False, False

    return LeadOutcome(lead_id=lead_id, label=label, converted=converted, negative=negative,
                       data_errors=data_errors, event_count=len(events), converted_via=converted_via)


def build_outcomes(events: Iterable[FeedbackEvent]) -> dict[Any, LeadOutcome]:
    by_lead: dict[Any, list[FeedbackEvent]] = defaultdict(list)
    for e in events:
        by_lead[e.lead_id].append(e)
    return {lid: reduce_lead(lid, evs) for lid, evs in by_lead.items()}


@dataclass(slots=True)
class GroupConversion:
    key: str
    leads: int
    converted: int
    negative: int
    decided: int
    conversion_rate: float      # converted / decided


@dataclass(slots=True)
class Precision:
    threshold: int
    high_leads: int
    decided: int
    converted: int
    precision: float | None     # converted / decided among high-score decided leads


@dataclass(slots=True)
class AnalyticsReport:
    total_events: int
    total_leads: int
    precision_high: Precision
    conversion_by_bucket: list[GroupConversion]
    conversion_by_event_type: list[GroupConversion]
    conversion_by_product: list[GroupConversion]
    conversion_by_sector: list[GroupConversion]
    false_positive_patterns: dict[str, list[tuple[str, int]]]
    false_negative_examples: list[dict]


def _group_conversion(key: str, lead_ids: list[Any], outcomes: dict[Any, LeadOutcome]) -> GroupConversion:
    present = [outcomes[l] for l in lead_ids if l in outcomes]
    converted = sum(1 for o in present if o.converted)
    negative = sum(1 for o in present if o.negative)
    decided = converted + negative
    return GroupConversion(key=key, leads=len(present), converted=converted, negative=negative,
                           decided=decided, conversion_rate=round(converted / decided, 3) if decided else 0.0)


class FeedbackAnalytics:
    def __init__(
        self,
        events: Iterable[FeedbackEvent],
        meta: dict[Any, LeadMeta],
        *,
        high_threshold: int = 80,
        low_threshold: int = 45,
        buckets: list[tuple[int, int]] | None = None,
    ) -> None:
        self._events = list(events)
        self._meta = meta
        self._high = high_threshold
        self._low = low_threshold
        self._buckets = buckets or DEFAULT_BUCKETS
        self._outcomes = build_outcomes(self._events)

    def compute(self) -> AnalyticsReport:
        outcomes, meta = self._outcomes, self._meta

        # Precision of high-scoring leads.
        high_ids = [lid for lid, m in meta.items() if m.score >= self._high]
        hi = _group_conversion("high", high_ids, outcomes)
        precision = Precision(
            threshold=self._high, high_leads=len([l for l in high_ids if l in outcomes]),
            decided=hi.decided, converted=hi.converted,
            precision=round(hi.converted / hi.decided, 3) if hi.decided else None,
        )

        # Conversion by score bucket.
        buckets: list[GroupConversion] = []
        for lo, hi_edge in self._buckets:
            ids = [lid for lid, m in meta.items() if lo <= m.score < hi_edge]
            buckets.append(_group_conversion(f"{lo}-{hi_edge - 1}", ids, outcomes))

        # Conversion by categorical dimensions.
        def by(attr: str) -> list[GroupConversion]:
            groups: dict[str, list[Any]] = defaultdict(list)
            for lid, m in meta.items():
                groups[getattr(m, attr) or "unknown"].append(lid)
            return sorted((_group_conversion(k, v, outcomes) for k, v in groups.items()),
                          key=lambda g: g.leads, reverse=True)

        # False-positive patterns: high-score leads that ended negative.
        fp_ids = [lid for lid in high_ids if lid in outcomes and outcomes[lid].negative]
        fp_patterns: dict[str, list[tuple[str, int]]] = {}
        for dim in ("product", "sector", "event_type"):
            counts: dict[str, int] = defaultdict(int)
            for lid in fp_ids:
                counts[getattr(meta[lid], dim) or "unknown"] += 1
            fp_patterns[dim] = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)

        # False-negative examples: low-score leads that nonetheless converted.
        fn_examples = [
            {"lead_id": lid, "company": meta[lid].company, "score": meta[lid].score,
             "grade": meta[lid].grade, "event_type": meta[lid].event_type,
             "product": meta[lid].product, "sector": meta[lid].sector,
             "converted_via": outcomes[lid].converted_via}
            for lid, m in meta.items()
            if m.score < self._low and lid in outcomes and outcomes[lid].converted
        ]
        fn_examples.sort(key=lambda d: d["score"])

        return AnalyticsReport(
            total_events=len(self._events), total_leads=len(outcomes),
            precision_high=precision, conversion_by_bucket=buckets,
            conversion_by_event_type=by("event_type"), conversion_by_product=by("product"),
            conversion_by_sector=by("sector"), false_positive_patterns=fp_patterns,
            false_negative_examples=fn_examples,
        )
