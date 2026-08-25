"""Scoring configuration — external, versioned, changeable without redeploy.

A ScoringConfig lists the components, each with its maximum points and optional
parameters. It can be loaded from a dict or JSON file (or a DB row); the app
never hardcodes the weights. Configs are versioned so different scoring
algorithms can be compared side by side.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass(slots=True)
class ComponentConfig:
    key: str
    label: str
    max_points: int
    params: dict = field(default_factory=dict)


@dataclass(slots=True)
class ScoringConfig:
    version: str
    components: list[ComponentConfig]

    def component(self, key: str) -> ComponentConfig | None:
        for c in self.components:
            if c.key == key:
                return c
        return None

    @property
    def total_max(self) -> int:
        return sum(c.max_points for c in self.components)

    def validate(self) -> None:
        if self.total_max != 100:
            raise ValueError(
                f"scoring config '{self.version}' component max_points sum to "
                f"{self.total_max}, expected 100"
            )

    # -- loaders ------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> ScoringConfig:
        cfg = cls(
            version=data["version"],
            components=[
                ComponentConfig(
                    key=c["key"], label=c["label"], max_points=int(c["max_points"]),
                    params=c.get("params", {}),
                )
                for c in data["components"]
            ],
        )
        cfg.validate()
        return cfg

    @classmethod
    def from_json(cls, path: str) -> ScoringConfig:
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "components": [
                {"key": c.key, "label": c.label, "max_points": c.max_points, "params": c.params}
                for c in self.components
            ],
        }


def default_config() -> ScoringConfig:
    """Ships as a sensible default; override via JSON/DB at runtime."""
    return ScoringConfig.from_dict({
        "version": "lead-score-v1",
        "components": [
            {"key": "sector_relevance", "label": "Sector relevance", "max_points": 25},
            {"key": "event_significance", "label": "Event significance", "max_points": 20,
             "params": {"value_full": 1_000_000_000,
                        "type_weights": {"contract_award": 1.0, "award": 1.0, "work_order": 0.9,
                                         "funding": 0.9, "tender": 0.6, "policy": 0.4, "scheme": 0.6,
                                         "approval": 0.5, "expansion": 0.7}}},
            {"key": "product_fit", "label": "Product fit", "max_points": 20,
             "params": {"full_at_confidence": 0.85}},
            {"key": "recency", "label": "Recency", "max_points": 15,
             "params": {"full_days": 30, "zero_days": 365}},
            {"key": "company_fit", "label": "Company fit", "max_points": 10},
            {"key": "contact_availability", "label": "Decision-maker availability", "max_points": 5},
            {"key": "evidence_confidence", "label": "Evidence confidence", "max_points": 5},
        ],
    })
