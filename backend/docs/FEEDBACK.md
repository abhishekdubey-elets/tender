# Sales Feedback System

Captures rep feedback as **immutable, append-only events**, derives per-lead
outcomes, reports conversion/precision analytics, and provides an **evaluation
harness** to compare scoring algorithms — **without** any ML retraining. The goal
is a reliable feedback dataset + reproducible evaluation first.

`app/feedback/`.

## Captured event types (`FeedbackEventType`)

lead_viewed · lead_accepted · lead_rejected · contacted · meeting_booked ·
opportunity_created · not_relevant · incorrect_company · incorrect_opportunity ·
incorrect_contact.

Each maps to an `OutcomeClass` (view / engaged / converted / negative /
data_error); the incorrect-* trio also flips a data-quality flag.

## Immutability

`FeedbackEvent` is a **frozen** dataclass; `InMemoryFeedbackStore` exposes only
`append` + read (no update/delete), and `events()` returns a copy. The DB writer
(`db.record_feedback`) only ever inserts `sales_feedback` rows (granular type
preserved in `notes`, mapped onto the schema's `FeedbackOutcome`,
`data_quality_flag` set for incorrect-* events).

## Analytics (`FeedbackAnalytics.compute()`)

Each lead's event stream is reduced to one outcome (conversion wins, then
negative/data-error, then engaged, then view). The report gives:

- **precision of high-scoring leads** — converted / decided among leads scored ≥
  threshold;
- **conversion by score bucket** (0-20 … 80-100);
- **conversion by event type / product / sector**;
- **false-positive patterns** — high-score leads that ended negative, grouped by
  product / sector / event type;
- **false-negative examples** — low-score leads that nonetheless converted.

## Evaluation harness (`evaluation.py`)

An `EvaluationExample` stores the exact `ScoringInput`, the `as_of` date, the
outcome label, and the original score + config version.

- `evaluate(examples, config, threshold)` → confusion matrix + precision / recall
  / F1 / accuracy, plus per-bucket conversion under that config.
- `compare_configs(examples, baseline, candidate)` → both metric sets and their
  deltas — the baseline-vs-new comparison, run offline before switching.
- `verify_reproducible(examples, configs)` → re-scores each example with the
  exact config it was originally scored under and returns any mismatches.
  Because scoring is deterministic in (config, input, as-of date), historical
  scores reproduce exactly; a tampered score is detected.

**No auto-retraining.** The system establishes the labelled dataset and the
comparison tooling; adopting a new scoring config remains a human decision
informed by `compare_configs`.

## Tests

`tests/test_feedback.py` — event immutability, append-only store, full
event-type coverage, per-lead reduction, precision / bucket / dimension
analytics, false-positive & false-negative surfacing, evaluate confusion matrix,
config comparison, and reproducibility (incl. tamper detection).

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_feedback.py -q
```
