"""Persist lead scores into ``lead_scores`` (with the transparent factor
breakdown and the config version, so scoring algorithms can be compared)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.enums import ScoreGrade
from app.db.models import LeadScore as LeadScoreRow
from app.scoring.types import LeadScore


def persist_lead_score(
    session: Session, opportunity_id: Any, lead_score: LeadScore, *, mark_current: bool = True
) -> LeadScoreRow:
    if mark_current:
        session.execute(
            update(LeadScoreRow)
            .where(LeadScoreRow.opportunity_id == opportunity_id, LeadScoreRow.is_current.is_(True))
            .values(is_current=False)
        )
    row = LeadScoreRow(
        opportunity_id=opportunity_id,
        score=lead_score.total,
        grade=ScoreGrade[lead_score.grade],
        factors=lead_score.to_factors(),
        model_version=lead_score.config_version,
        is_current=mark_current,
        scored_at=lead_score.scored_at,
    )
    session.add(row)
    session.flush()
    return row
