"""Transparent Lead Scoring Engine.

Produces a 100-point lead score from configurable components (sector relevance,
event significance, product fit, recency, company fit, decision-maker
availability, evidence confidence). Weights live in an external, versioned
configuration — not hardcoded — so scoring can change without redeploying. Every
score stores its per-component breakdown so the UI can explain
"why is this lead 91/100?".
"""
from __future__ import annotations

from app.scoring.config import ComponentConfig, ScoringConfig, default_config
from app.scoring.engine import LeadScoringEngine
from app.scoring.types import LeadScore, ScoreComponent, ScoringInput

__all__ = [
    "LeadScoringEngine",
    "ScoringConfig",
    "ComponentConfig",
    "default_config",
    "LeadScore",
    "ScoreComponent",
    "ScoringInput",
]
