"""Evaluation pipeline: compare a baseline scoring config against a new one over
the labelled feedback dataset, and verify historical scores are reproducible.

Reproducibility rests on the scorer being deterministic given (config, input,
as-of date). Each example therefore stores the exact ScoringInput and the
`as_of` date used, so re-scoring reproduces the original total exactly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.feedback.analytics import DEFAULT_BUCKETS, GroupConversion
from app.scoring.config import ScoringConfig
from app.scoring.engine import LeadScoringEngine
from app.scoring.types import ScoringInput


@dataclass(slots=True)
class EvaluationExample:
    lead_id: Any
    scoring_input: ScoringInput
    as_of: date
    converted: bool
    negative: bool
    original_total: int | None = None
    original_version: str | None = None
    event_type: str | None = None
    product: str | None = None
    sector: str | None = None

    @property
    def decided(self) -> bool:
        return self.converted or self.negative


@dataclass(slots=True)
class EvalMetrics:
    config_version: str
    threshold: int
    n: int
    tp: int
    fp: int
    tn: int
    fn: int
    precision: float | None
    recall: float | None
    f1: float | None
    accuracy: float | None
    buckets: list[GroupConversion] = field(default_factory=list)


def _safe_div(a: float, b: float) -> float | None:
    return round(a / b, 3) if b else None


def evaluate(
    examples: list[EvaluationExample],
    config: ScoringConfig,
    *,
    threshold: int = 80,
    buckets: list[tuple[int, int]] | None = None,
) -> EvalMetrics:
    engine = LeadScoringEngine(config)
    buckets = buckets or DEFAULT_BUCKETS
    tp = fp = tn = fn = 0
    bucket_ct = {b: [0, 0] for b in buckets}   # (converted, decided)

    for ex in examples:
        if not ex.decided:
            continue
        total = engine.score(ex.scoring_input, as_of=ex.as_of).total
        predicted_positive = total >= threshold
        actual_positive = ex.converted
        if predicted_positive and actual_positive:
            tp += 1
        elif predicted_positive:
            fp += 1
        elif actual_positive:
            fn += 1
        else:
            tn += 1
        for (lo, hi) in buckets:
            if lo <= total < hi:
                bucket_ct[(lo, hi)][1] += 1
                if actual_positive:
                    bucket_ct[(lo, hi)][0] += 1
                break

    n = tp + fp + tn + fn
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = round(2 * precision * recall / (precision + recall), 3) if precision and recall else None
    buckets_out = [
        GroupConversion(key=f"{lo}-{hi - 1}", leads=dec, converted=conv, negative=dec - conv,
                        decided=dec, conversion_rate=round(conv / dec, 3) if dec else 0.0)
        for (lo, hi), (conv, dec) in bucket_ct.items()
    ]
    return EvalMetrics(
        config_version=config.version, threshold=threshold, n=n,
        tp=tp, fp=fp, tn=tn, fn=fn,
        precision=precision, recall=recall, f1=f1, accuracy=_safe_div(tp + tn, n),
        buckets=buckets_out,
    )


def compare_configs(
    examples: list[EvaluationExample],
    baseline: ScoringConfig,
    new: ScoringConfig,
    *,
    threshold: int = 80,
) -> dict:
    b = evaluate(examples, baseline, threshold=threshold)
    m = evaluate(examples, new, threshold=threshold)

    def delta(x: float | None, y: float | None) -> float | None:
        return round((y or 0) - (x or 0), 3) if (x is not None or y is not None) else None

    return {
        "baseline": b, "candidate": m,
        "delta": {"precision": delta(b.precision, m.precision), "recall": delta(b.recall, m.recall),
                  "f1": delta(b.f1, m.f1), "accuracy": delta(b.accuracy, m.accuracy)},
    }


def verify_reproducible(
    examples: list[EvaluationExample], configs: dict[str, ScoringConfig]
) -> list[dict]:
    """Re-score each example with the exact config it was originally scored under;
    return any mismatches (empty list == fully reproducible)."""
    mismatches: list[dict] = []
    for ex in examples:
        if ex.original_total is None or ex.original_version is None:
            continue
        cfg = configs.get(ex.original_version)
        if cfg is None:
            mismatches.append({"lead_id": ex.lead_id, "reason": f"config '{ex.original_version}' not available"})
            continue
        total = LeadScoringEngine(cfg).score(ex.scoring_input, as_of=ex.as_of).total
        if total != ex.original_total:
            mismatches.append({"lead_id": ex.lead_id, "expected": ex.original_total, "got": total,
                               "version": ex.original_version})
    return mismatches
