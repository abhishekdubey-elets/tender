"""Scoring inputs and outputs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(slots=True)
class ScoringInput:
    """The signals a lead score is computed from (decoupled from ORM)."""

    event_type: str
    event_value: float | None = None
    event_date: date | None = None
    event_sector: str | None = None

    company_industry: str | None = None
    company_employee_range: str | None = None

    target_sectors: list[str] = field(default_factory=list)
    target_min_value: float | None = None
    ideal_employee_ranges: list[str] | None = None

    opportunity_confidence: float | None = None      # product-fit signal (0..1)
    evidence_confidences: list[float] = field(default_factory=list)

    num_contacts: int = 0
    best_contact_seniority: str | None = None


@dataclass(slots=True)
class ScoreComponent:
    key: str
    label: str
    points: int
    max_points: int
    explanation: str
    detail: dict = field(default_factory=dict)


@dataclass(slots=True)
class LeadScore:
    total: int
    grade: str                       # A..F
    components: list[ScoreComponent]
    config_version: str
    scored_at: datetime

    def to_factors(self) -> dict:
        """JSONB payload for ``lead_scores.factors`` — the transparent breakdown."""
        return {
            "total": self.total,
            "grade": self.grade,
            "config_version": self.config_version,
            "components": [
                {"key": c.key, "label": c.label, "points": c.points,
                 "max_points": c.max_points, "explanation": c.explanation, "detail": c.detail}
                for c in self.components
            ],
        }

    def explain(self) -> str:
        """Human-readable 'why is this lead X/100?'."""
        lines = [f"Lead score {self.total}/100 (grade {self.grade}, {self.config_version}):"]
        for c in self.components:
            lines.append(f"  - {c.label}: {c.points}/{c.max_points} — {c.explanation}")
        return "\n".join(lines)
