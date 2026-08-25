"""LeadScoringEngine: run the configured components, sum, grade, version."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone

from app.scoring.components import SCORERS
from app.scoring.config import ScoringConfig, default_config
from app.scoring.types import LeadScore, ScoreComponent, ScoringInput


def _grade(total: int) -> str:
    if total >= 80:
        return "A"
    if total >= 65:
        return "B"
    if total >= 45:
        return "C"
    if total >= 25:
        return "D"
    return "F"


class LeadScoringEngine:
    def __init__(
        self,
        config: ScoringConfig | None = None,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._config = config or default_config()
        self._config.validate()
        self._now = now

    @property
    def config(self) -> ScoringConfig:
        return self._config

    def score(self, inp: ScoringInput, *, as_of: date | None = None) -> LeadScore:
        now_dt = self._now()
        today = as_of or now_dt.date()

        components: list[ScoreComponent] = []
        for component_cfg in self._config.components:
            scorer = SCORERS.get(component_cfg.key)
            if scorer is None:
                # Unknown component in config → surfaced as a zero with a note,
                # never silently ignored.
                components.append(ScoreComponent(
                    component_cfg.key, component_cfg.label, 0, component_cfg.max_points,
                    "no scorer registered for this component", {},
                ))
                continue
            components.append(scorer(inp, component_cfg, now=today))

        total = sum(c.points for c in components)   # rounded components sum exactly
        return LeadScore(
            total=total,
            grade=_grade(total),
            components=components,
            config_version=self._config.version,
            scored_at=now_dt,
        )
