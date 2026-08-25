"""Lead board, detail and feedback endpoints (org-scoped, rate-limited)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.schemas import FeedbackAck, FeedbackIn, LeadDetail, LeadSummary
from app.api.security import Principal, rate_limit

router = APIRouter(prefix="/api", tags=["leads"])


@router.get("/leads", response_model=list[LeadSummary])
def list_leads(
    request: Request,
    principal: Principal = Depends(rate_limit),
    score_min: int = Query(0, ge=0, le=100),
    sector: str | None = None,
    product: str | None = None,
    event_type: str | None = None,
    gov_org: str | None = None,
    status_: str | None = Query(None, alias="status"),
    company: str | None = Query(None, max_length=120),
    date_days: int | None = Query(None, ge=1, le=3650),
):
    filters = {"score_min": score_min, "sector": sector, "product": product,
               "event_type": event_type, "gov_org": gov_org, "status": status_,
               "company": company, "date_days": date_days}
    return request.app.state.repository.list_leads(principal.organization_id, filters)


@router.get("/leads/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: str, request: Request, principal: Principal = Depends(rate_limit)):
    lead = request.app.state.repository.get_lead(principal.organization_id, lead_id)
    if lead is None:
        # Same 404 whether the lead doesn't exist or belongs to another org
        # (no cross-tenant existence leak).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return lead


@router.post("/leads/{lead_id}/feedback", response_model=FeedbackAck)
def post_feedback(lead_id: str, body: FeedbackIn, request: Request,
                  principal: Principal = Depends(rate_limit)):
    if not principal.can_write_feedback():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted to submit feedback")
    result = request.app.state.repository.record_feedback(
        principal.organization_id, lead_id, body.event_type, body.note, principal.api_key_id)
    if not result["ok"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return FeedbackAck(lead_id=lead_id, event_type=body.event_type, status=result["status"])
