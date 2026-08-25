"""Persist a generated brief into ``sales_briefs`` with model metadata."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.brief.types import SalesBrief
from app.db.enums import BriefFormat, BriefStatus
from app.db.models import SalesBrief as SalesBriefRow


def persist_brief(
    session: Session,
    opportunity_id: Any,
    brief: SalesBrief,
    *,
    contact_id: Any = None,
    generated_by_user_id: Any = None,
) -> SalesBriefRow:
    # A flagged brief (had unsupported claims stripped) stays a draft for review;
    # a clean brief is final.
    status = BriefStatus.final if brief.status == "ok" else BriefStatus.draft
    row = SalesBriefRow(
        opportunity_id=opportunity_id,
        contact_id=contact_id,
        generated_by_user_id=generated_by_user_id,
        content=brief.render(),
        format=BriefFormat.markdown,
        status=status,
        model=brief.meta.model,
        prompt_version=brief.meta.prompt_version,
        input_tokens=brief.meta.input_tokens,
        output_tokens=brief.meta.output_tokens,
        generated_at=brief.meta.generated_at,
    )
    session.add(row)
    session.flush()
    return row
