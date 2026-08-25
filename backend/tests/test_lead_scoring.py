"""Transparent lead scoring: high/medium/low leads, breakdown, versioning."""
from __future__ import annotations

from datetime import date

import pytest

from app.scoring import LeadScoringEngine, ScoringConfig, ScoringInput, default_config

AS_OF = date(2026, 8, 25)
ENGINE = LeadScoringEngine()


def _score(inp: ScoringInput, engine: LeadScoringEngine = ENGINE):
    return engine.score(inp, as_of=AS_OF)


HIGH = ScoringInput(
    event_type="contract_award", event_value=1_000_000_000, event_date=date(2026, 8, 20),
    event_sector="Defence", company_industry="Defence", company_employee_range="1001-5000",
    target_sectors=["Defence"], ideal_employee_ranges=["1001-5000"],
    opportunity_confidence=0.9, evidence_confidences=[0.9, 0.92],
    num_contacts=2, best_contact_seniority="c_level",
)

MEDIUM = ScoringInput(
    event_type="tender", event_value=50_000_000, event_date=date(2026, 5, 1),
    event_sector="Smart Cities", company_industry="IT",
    target_sectors=["Smart Cities", "BFSI"],
    opportunity_confidence=0.5, evidence_confidences=[0.5],
    num_contacts=0,
)

LOW = ScoringInput(
    event_type="policy", event_value=None, event_date=date(2024, 1, 1),
    event_sector="Agriculture", target_sectors=["Defence"],
    opportunity_confidence=0.2, num_contacts=0,
)


# --- quality bands ----------------------------------------------------------
def test_high_quality_lead_scores_high() -> None:
    result = _score(HIGH)
    assert result.total >= 85
    assert result.grade == "A"
    # component maxima honoured
    comp = {c.key: c for c in result.components}
    assert comp["sector_relevance"].points == 25
    assert comp["product_fit"].points == 20


def test_medium_quality_lead_scores_mid() -> None:
    result = _score(MEDIUM)
    assert 45 <= result.total < 70
    assert result.grade in {"B", "C"}


def test_low_quality_lead_scores_low() -> None:
    result = _score(LOW)
    assert result.total < 25
    assert result.grade in {"D", "F"}


# --- transparency -----------------------------------------------------------
def test_components_are_stored_and_sum_to_total() -> None:
    result = _score(HIGH)
    assert len(result.components) == 7
    assert sum(c.points for c in result.components) == result.total     # explainable invariant
    for c in result.components:
        assert 0 <= c.points <= c.max_points
        assert c.explanation


def test_factors_and_explain_answer_why() -> None:
    result = _score(HIGH)
    factors = result.to_factors()
    assert factors["total"] == result.total
    assert {c["key"] for c in factors["components"]} == {
        "sector_relevance", "event_significance", "product_fit", "recency",
        "company_fit", "contact_availability", "evidence_confidence",
    }
    text = result.explain()
    assert f"Lead score {result.total}/100" in text
    assert "Sector relevance" in text


# --- versioning & configurability -------------------------------------------
def test_score_versioning_allows_comparison() -> None:
    v2 = ScoringConfig.from_dict({
        "version": "lead-score-v2-sector-heavy",
        "components": [
            {"key": "sector_relevance", "label": "Sector relevance", "max_points": 40},
            {"key": "event_significance", "label": "Event significance", "max_points": 15},
            {"key": "product_fit", "label": "Product fit", "max_points": 15,
             "params": {"full_at_confidence": 0.85}},
            {"key": "recency", "label": "Recency", "max_points": 10},
            {"key": "company_fit", "label": "Company fit", "max_points": 10},
            {"key": "contact_availability", "label": "Decision-maker availability", "max_points": 5},
            {"key": "evidence_confidence", "label": "Evidence confidence", "max_points": 5},
        ],
    })
    r1 = _score(HIGH)
    r2 = _score(HIGH, LeadScoringEngine(v2))
    assert r1.config_version == "lead-score-v1"
    assert r2.config_version == "lead-score-v2-sector-heavy"
    # Same lead, different algorithm → comparable, versioned results.
    assert r1.total != r2.total or r1.config_version != r2.config_version


def test_config_can_change_weights_without_code() -> None:
    data = default_config().to_dict()
    data["version"] = "custom-v9"
    data["components"][0]["max_points"] = 30      # sector 25 -> 30
    data["components"][1]["max_points"] = 15      # event 20 -> 15  (still sums to 100)
    cfg = ScoringConfig.from_dict(data)
    result = LeadScoringEngine(cfg).score(HIGH, as_of=AS_OF)
    assert result.config_version == "custom-v9"
    assert next(c for c in result.components if c.key == "sector_relevance").max_points == 30


def test_invalid_config_rejected() -> None:
    with pytest.raises(ValueError):
        ScoringConfig.from_dict({
            "version": "bad",
            "components": [{"key": "sector_relevance", "label": "S", "max_points": 50}],  # != 100
        })
