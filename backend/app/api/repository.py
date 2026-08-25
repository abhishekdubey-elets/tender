"""Lead data access. Protocol + in-memory implementation.

The in-memory repo powers the dashboard demo and the tests; a SQLAlchemy-backed
implementation reads the same shape from government_events / companies /
opportunities / lead_scores / sales_briefs / contacts.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

from app.feedback.store import InMemoryFeedbackStore
from app.feedback.types import FeedbackEvent, FeedbackEventType


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return (date.today() - date.fromisoformat(iso)).days
    except ValueError:
        return None


def _summary(lead: dict) -> dict:
    keys = ("id", "company", "status", "event", "opportunity", "opportunity_tier",
            "score", "grade", "confidence", "why_now", "reason_to_call", "target_contact")
    return {k: lead[k] for k in keys}


@runtime_checkable
class LeadRepository(Protocol):
    def list_leads(self, organization_id: str, filters: dict) -> list[dict]: ...

    def get_lead(self, organization_id: str, lead_id: str) -> dict | None: ...

    def record_feedback(self, organization_id: str, lead_id: str,
                        event_type: FeedbackEventType, note: str | None, actor: str) -> dict: ...


class InMemoryLeadRepository:
    def __init__(self, feedback_store: InMemoryFeedbackStore | None = None) -> None:
        self._leads: dict[str, dict] = {}
        self.feedback = feedback_store or InMemoryFeedbackStore()

    def add(self, lead: dict) -> None:
        self._leads[lead["id"]] = lead

    def _scoped(self, organization_id: str) -> list[dict]:
        return [l for l in self._leads.values() if l.get("organization_id") == organization_id]

    def list_leads(self, organization_id: str, filters: dict) -> list[dict]:
        out = []
        for l in self._scoped(organization_id):
            if l["score"] < filters.get("score_min", 0):
                continue
            if (s := filters.get("sector")) and l["event"].get("sector") != s:
                continue
            if (p := filters.get("product")) and l["opportunity"] != p:
                continue
            if (et := filters.get("event_type")) and l["event"].get("type_label") != et:
                continue
            if (org := filters.get("gov_org")) and l["event"].get("org") != org:
                continue
            if (st := filters.get("status")) and l["status"] != st:
                continue
            if (co := filters.get("company")) and co.lower() not in l["company"].lower():
                continue
            if (dd := filters.get("date_days")):
                age = _days_since(l["event"].get("date"))
                if age is None or age > dd:
                    continue
            out.append(_summary(l))
        out.sort(key=lambda x: x["score"], reverse=True)
        return out

    def get_lead(self, organization_id: str, lead_id: str) -> dict | None:
        lead = self._leads.get(lead_id)
        if lead is None or lead.get("organization_id") != organization_id:
            return None
        return lead

    def record_feedback(self, organization_id: str, lead_id: str,
                        event_type: FeedbackEventType, note: str | None, actor: str) -> dict:
        lead = self.get_lead(organization_id, lead_id)
        if lead is None:
            return {"ok": False, "reason": "not_found"}
        from datetime import datetime, timezone
        self.feedback.append(FeedbackEvent(
            lead_id=lead_id, event_type=event_type, occurred_at=datetime.now(timezone.utc),
            actor_user_id=actor, note=note, score_at_event=lead["score"],
            config_version=lead.get("config_version")))
        # Reflect the status change back onto the lead (mirrors the dashboard).
        new_status = {
            FeedbackEventType.lead_accepted: "qualified",
            FeedbackEventType.opportunity_created: "qualified",
            FeedbackEventType.contacted: "contacted",
            FeedbackEventType.meeting_booked: "meeting",
            FeedbackEventType.lead_rejected: "disqualified",
            FeedbackEventType.not_relevant: "disqualified",
        }.get(event_type)
        if new_status:
            lead["status"] = new_status
        return {"ok": True, "status": lead["status"]}
