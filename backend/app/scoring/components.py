"""Per-component scorers. Each returns 0..max_points with an explanation, so the
total is always decomposable ("why 91/100?")."""
from __future__ import annotations

from datetime import date

from app.scoring.config import ComponentConfig
from app.scoring.types import ScoreComponent, ScoringInput


def _pts(fraction: float, max_points: int) -> int:
    return int(round(max(0.0, min(1.0, fraction)) * max_points))


def _sector_match(inp: ScoringInput) -> bool:
    targets = [t.lower() for t in inp.target_sectors]
    for cand in (inp.event_sector, inp.company_industry):
        if cand and any(t in cand.lower() or cand.lower() in t for t in targets):
            return True
    return False


def score_sector_relevance(inp: ScoringInput, cfg: ComponentConfig, *, now: date) -> ScoreComponent:
    if not inp.target_sectors:
        pts, expl = _pts(0.5, cfg.max_points), "no target sectors configured (neutral)"
    elif _sector_match(inp):
        pts, expl = cfg.max_points, "event/company sector matches a target sector"
    else:
        pts, expl = 0, "sector not among the target sectors"
    return ScoreComponent(cfg.key, cfg.label, pts, cfg.max_points, expl,
                          {"event_sector": inp.event_sector, "targets": inp.target_sectors})


def score_event_significance(inp: ScoringInput, cfg: ComponentConfig, *, now: date) -> ScoreComponent:
    value_full = cfg.params.get("value_full", 1_000_000_000)
    type_weights = cfg.params.get("type_weights", {})
    value_score = min(1.0, inp.event_value / value_full) if inp.event_value else 0.3
    type_w = type_weights.get(inp.event_type, 0.6)
    fraction = 0.7 * value_score + 0.3 * type_w
    pts = _pts(fraction, cfg.max_points)
    expl = f"{inp.event_type} valued at {inp.event_value or 'unknown'} (value {value_score:.0%}, type {type_w:.0%})"
    return ScoreComponent(cfg.key, cfg.label, pts, cfg.max_points, expl,
                          {"value": inp.event_value, "value_score": round(value_score, 3), "type_weight": type_w})


def score_product_fit(inp: ScoringInput, cfg: ComponentConfig, *, now: date) -> ScoreComponent:
    full_at = cfg.params.get("full_at_confidence", 0.85)
    conf = inp.opportunity_confidence or 0.0
    fraction = conf / full_at if full_at else conf
    pts = _pts(fraction, cfg.max_points)
    expl = f"opportunity confidence {conf:.2f} (full at {full_at:.2f})"
    return ScoreComponent(cfg.key, cfg.label, pts, cfg.max_points, expl, {"opportunity_confidence": conf})


def score_recency(inp: ScoringInput, cfg: ComponentConfig, *, now: date) -> ScoreComponent:
    full_days = cfg.params.get("full_days", 30)
    zero_days = cfg.params.get("zero_days", 365)
    if inp.event_date is None:
        return ScoreComponent(cfg.key, cfg.label, _pts(0.3, cfg.max_points), cfg.max_points,
                              "event date unknown (modest credit)", {})
    age = (now - inp.event_date).days
    if age <= full_days:
        fraction = 1.0
    elif age >= zero_days:
        fraction = 0.0
    else:
        fraction = 1.0 - (age - full_days) / (zero_days - full_days)
    pts = _pts(fraction, cfg.max_points)
    return ScoreComponent(cfg.key, cfg.label, pts, cfg.max_points,
                          f"event is {age} day(s) old", {"age_days": age})


def score_company_fit(inp: ScoringInput, cfg: ComponentConfig, *, now: date) -> ScoreComponent:
    fraction = 0.0
    notes = []
    if inp.company_industry:
        fraction += 0.4
        notes.append("industry known")
    if inp.company_employee_range:
        if inp.ideal_employee_ranges and inp.company_employee_range in inp.ideal_employee_ranges:
            fraction += 0.6
            notes.append("size matches ICP")
        else:
            fraction += 0.3
            notes.append("size known")
    expl = ", ".join(notes) or "little is known about the company"
    return ScoreComponent(cfg.key, cfg.label, _pts(fraction, cfg.max_points), cfg.max_points, expl,
                          {"employee_range": inp.company_employee_range})


_SENIORITY_WEIGHT = {"c_level": 1.0, "vp": 0.85, "director": 0.8, "head": 0.8, "manager": 0.6}


def score_contact_availability(inp: ScoringInput, cfg: ComponentConfig, *, now: date) -> ScoreComponent:
    if inp.num_contacts <= 0:
        return ScoreComponent(cfg.key, cfg.label, 0, cfg.max_points, "no decision-maker contacts yet", {})
    w = _SENIORITY_WEIGHT.get(inp.best_contact_seniority or "", 0.5)
    pts = _pts(w, cfg.max_points)
    expl = f"{inp.num_contacts} contact(s); best seniority '{inp.best_contact_seniority or 'unknown'}'"
    return ScoreComponent(cfg.key, cfg.label, pts, cfg.max_points, expl,
                          {"num_contacts": inp.num_contacts, "seniority": inp.best_contact_seniority})


def score_evidence_confidence(inp: ScoringInput, cfg: ComponentConfig, *, now: date) -> ScoreComponent:
    confs = inp.evidence_confidences or ([inp.opportunity_confidence] if inp.opportunity_confidence else [])
    confs = [c for c in confs if c is not None]
    mean = sum(confs) / len(confs) if confs else 0.3
    pts = _pts(mean, cfg.max_points)
    return ScoreComponent(cfg.key, cfg.label, pts, cfg.max_points,
                          f"mean supporting-evidence confidence {mean:.2f}", {"mean_confidence": round(mean, 3)})


SCORERS = {
    "sector_relevance": score_sector_relevance,
    "event_significance": score_event_significance,
    "product_fit": score_product_fit,
    "recency": score_recency,
    "company_fit": score_company_fit,
    "contact_availability": score_contact_availability,
    "evidence_confidence": score_evidence_confidence,
}
