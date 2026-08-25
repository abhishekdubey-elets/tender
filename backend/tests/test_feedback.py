"""Sales feedback: immutable events, analytics, evaluation & reproducibility."""
from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone

import pytest

from app.feedback import (
    EVENT_CLASS,
    FeedbackAnalytics,
    FeedbackEvent,
    FeedbackEventType as FT,
    InMemoryFeedbackStore,
    LeadMeta,
    OutcomeClass,
    compare_configs,
    evaluate,
    verify_reproducible,
)
from app.feedback.analytics import reduce_lead
from app.feedback.db import _OUTCOME_MAP
from app.scoring import LeadScoringEngine, ScoringConfig, ScoringInput, default_config

NOW = datetime(2026, 8, 25, tzinfo=timezone.utc)


def ev(lead, t: FT) -> FeedbackEvent:
    return FeedbackEvent(lead_id=lead, event_type=t, occurred_at=NOW)


# --- immutability ------------------------------------------------------------
def test_feedback_event_is_immutable() -> None:
    e = ev("L1", FT.meeting_booked)
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.event_type = FT.lead_rejected  # type: ignore[misc]


def test_store_is_append_only() -> None:
    store = InMemoryFeedbackStore()
    store.append(ev("L1", FT.lead_viewed))
    store.append(ev("L1", FT.meeting_booked))
    assert len(store) == 2
    assert not hasattr(store, "delete") and not hasattr(store, "update")
    # returned list is a copy — mutating it doesn't affect the log
    store.events().clear()
    assert len(store) == 2


def test_all_event_types_are_classified_and_mapped() -> None:
    for t in FT:
        assert t in EVENT_CLASS
        assert t in _OUTCOME_MAP


# --- per-lead reduction ------------------------------------------------------
def test_reduce_prefers_conversion_then_negative() -> None:
    o = reduce_lead("L", [ev("L", FT.lead_viewed), ev("L", FT.contacted), ev("L", FT.meeting_booked)])
    assert o.label is OutcomeClass.converted and o.converted and not o.negative
    o2 = reduce_lead("L", [ev("L", FT.lead_viewed), ev("L", FT.not_relevant)])
    assert o2.negative and o2.label is OutcomeClass.negative
    o3 = reduce_lead("L", [ev("L", FT.incorrect_company)])
    assert o3.negative and "incorrect_company" in o3.data_errors
    o4 = reduce_lead("L", [ev("L", FT.lead_viewed)])
    assert o4.label is OutcomeClass.view


# --- analytics ---------------------------------------------------------------
def _analytics_fixture():
    meta = {
        "L1": LeadMeta("L1", 91, "A", "contract_award", "cybersecurity", "Defence", "Acme"),
        "L2": LeadMeta("L2", 84, "A", "work_order", "cloud_infrastructure", "Smart Cities", "Metro"),
        "L3": LeadMeta("L3", 88, "A", "funding", "events_sponsorship", "BFSI", "FinCo"),   # false positive
        "L4": LeadMeta("L4", 62, "B", "contract_award", "cloud_infrastructure", "Healthcare", "Bharat"),
        "L5": LeadMeta("L5", 55, "C", "work_order", "workforce_staffing", "Urban Infra", "Ganga"),
        "L6": LeadMeta("L6", 40, "C", "contract_award", "cybersecurity", "Defence", "Delta"),  # false negative
        "L7": LeadMeta("L7", 30, "D", "funding", "events_sponsorship", "Education", "EduN"),   # false negative
        "L8": LeadMeta("L8", 20, "F", "approval", "events_sponsorship", "BFSI", "Zeta"),
    }
    events = []
    for lid in meta:
        events.append(ev(lid, FT.lead_viewed))
    events += [
        ev("L1", FT.meeting_booked), ev("L2", FT.opportunity_created), ev("L3", FT.not_relevant),
        ev("L4", FT.opportunity_created), ev("L5", FT.lead_rejected),
        ev("L6", FT.opportunity_created), ev("L7", FT.meeting_booked), ev("L8", FT.not_relevant),
    ]
    return events, meta


def test_precision_of_high_scoring_leads() -> None:
    events, meta = _analytics_fixture()
    r = FeedbackAnalytics(events, meta, high_threshold=80).compute()
    # high = L1,L2 converted; L3 negative -> precision 2/3
    assert r.precision_high.high_leads == 3
    assert r.precision_high.converted == 2
    assert r.precision_high.precision == round(2 / 3, 3)


def test_conversion_by_bucket_and_dimensions() -> None:
    events, meta = _analytics_fixture()
    r = FeedbackAnalytics(events, meta).compute()
    top_bucket = next(b for b in r.conversion_by_bucket if b.key == "80-100")
    assert (top_bucket.converted, top_bucket.negative) == (2, 1)
    # every categorical breakdown is present
    assert any(g.key == "cybersecurity" for g in r.conversion_by_product)
    assert any(g.key == "Defence" for g in r.conversion_by_sector)
    assert any(g.key == "contract_award" for g in r.conversion_by_event_type)


def test_false_positive_patterns_and_false_negatives() -> None:
    events, meta = _analytics_fixture()
    r = FeedbackAnalytics(events, meta, high_threshold=80, low_threshold=45).compute()
    # L3 is the only high-score negative → events_sponsorship / BFSI / funding
    assert ("events_sponsorship", 1) in r.false_positive_patterns["product"]
    assert ("BFSI", 1) in r.false_positive_patterns["sector"]
    # L6 (40) and L7 (30) converted despite low scores
    fn_ids = {e["lead_id"] for e in r.false_negative_examples}
    assert fn_ids == {"L6", "L7"}
    assert r.false_negative_examples[0]["score"] <= r.false_negative_examples[1]["score"]


# --- evaluation & reproducibility -------------------------------------------
def _example_inputs():
    """Inputs whose default score lands high / low, with labels."""
    strong = ScoringInput(event_type="contract_award", event_value=1e9, event_date=date(2026, 8, 20),
                          event_sector="Defence", company_industry="Defence", company_employee_range="1001-5000",
                          target_sectors=["Defence"], ideal_employee_ranges=["1001-5000"],
                          opportunity_confidence=0.9, evidence_confidences=[0.9], num_contacts=1,
                          best_contact_seniority="c_level")
    weak = ScoringInput(event_type="tender", event_value=1e6, event_date=date(2024, 1, 1),
                        event_sector="Agriculture", target_sectors=["Defence"], opportunity_confidence=0.2)
    return strong, weak


def _dataset():
    strong, weak = _example_inputs()
    eng = LeadScoringEngine(default_config())
    as_of = date(2026, 8, 25)
    from app.feedback.evaluation import EvaluationExample
    mk = lambda lid, inp, conv, neg: EvaluationExample(
        lead_id=lid, scoring_input=inp, as_of=as_of, converted=conv, negative=neg,
        original_total=eng.score(inp, as_of=as_of).total, original_version="lead-score-v1")
    return [
        mk("H-conv", strong, True, False),   # high & converted -> TP
        mk("H-neg", strong, False, True),    # high & negative  -> FP
        mk("L-conv", weak, True, False),     # low & converted  -> FN
        mk("L-neg", weak, False, True),      # low & negative   -> TN
    ]


def test_evaluate_produces_confusion_metrics() -> None:
    m = evaluate(_dataset(), default_config(), threshold=80)
    assert (m.tp, m.fp, m.fn, m.tn) == (1, 1, 1, 1)
    assert m.precision == 0.5 and m.recall == 0.5

def test_compare_configs_reports_delta() -> None:
    baseline = default_config()
    heavy = ScoringConfig.from_dict({
        "version": "sector-heavy-v2",
        "components": [
            {"key": "sector_relevance", "label": "Sector", "max_points": 45},
            {"key": "event_significance", "label": "Event", "max_points": 15},
            {"key": "product_fit", "label": "Product", "max_points": 15},
            {"key": "recency", "label": "Recency", "max_points": 10},
            {"key": "company_fit", "label": "Company", "max_points": 5},
            {"key": "contact_availability", "label": "Contact", "max_points": 5},
            {"key": "evidence_confidence", "label": "Evidence", "max_points": 5},
        ],
    })
    result = compare_configs(_dataset(), baseline, heavy, threshold=80)
    assert result["baseline"].config_version == "lead-score-v1"
    assert result["candidate"].config_version == "sector-heavy-v2"
    assert set(result["delta"]) == {"precision", "recall", "f1", "accuracy"}


def test_historical_scores_are_reproducible() -> None:
    dataset = _dataset()
    configs = {"lead-score-v1": default_config()}
    assert verify_reproducible(dataset, configs) == []      # deterministic re-scoring matches
    # tamper a stored score → detected
    dataset[0] = dataclasses.replace(dataset[0], original_total=dataset[0].original_total + 5)
    mism = verify_reproducible(dataset, configs)
    assert len(mism) == 1 and mism[0]["lead_id"] == "H-conv"
