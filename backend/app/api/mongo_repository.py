"""MongoDB-backed lead repository — Phase 1 of the Postgres → Mongo migration.

Serves the dashboard (board / detail / feedback) from a single ``leads`` collection
of denormalized documents — the same summary+detail shape the SQL repo produces —
so the read API is a drop-in. Selected via ``USE_MONGO`` + ``MONGODB_URI``; the
Postgres path is left untouched behind the flag.

Real-time push uses MongoDB **change streams** (Atlas is a replica set) instead of
Postgres LISTEN/NOTIFY: any write to ``leads`` broadcasts a content-free
``leads_changed`` signal to WebSocket clients.

pymongo is imported lazily (inside the client constructor) so importing this module
never requires the driver — only running with ``USE_MONGO=true`` does.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
from datetime import date, datetime, timedelta, timezone

from app.feedback.types import FeedbackEventType

logger = logging.getLogger("govintel.api")

# Fields projected for the board (must match app.api.repository._summary).
_SUMMARY_KEYS = ("id", "company", "status", "event", "opportunity", "opportunity_tier",
                 "score", "grade", "confidence", "why_now", "reason_to_call", "target_contact")

# Feedback action → new lead status (mirrors the SQL/in-memory repositories).
_STATUS_BY_EVENT = {
    FeedbackEventType.lead_accepted: "qualified",
    FeedbackEventType.opportunity_created: "qualified",
    FeedbackEventType.contacted: "contacted",
    FeedbackEventType.meeting_booked: "meeting",
    FeedbackEventType.lead_rejected: "disqualified",
    FeedbackEventType.not_relevant: "disqualified",
}


def _to_dt(iso: str | None) -> datetime | None:
    """ISO date string → tz-aware UTC midnight (for sort + date_days); None if absent."""
    if not iso:
        return None
    try:
        d = date.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


class MongoLeadRepository:
    def __init__(self, uri: str, db_name: str = "govintel") -> None:
        from pymongo import MongoClient

        self._client = MongoClient(uri, serverSelectionTimeoutMS=8000, appname="govintel", tz_aware=True)
        self._db = self._client[db_name]
        self.leads = self._db["leads"]
        self.feedback = self._db["sales_feedback"]

    # -- schema / indexes ---------------------------------------------------
    def ensure_indexes(self) -> None:
        self.leads.create_index([("organization_id", 1), ("event_date", -1), ("score", -1)])
        self.leads.create_index([("organization_id", 1), ("score", -1)])
        self.leads.create_index([("organization_id", 1), ("event.sector", 1)])
        self.leads.create_index([("organization_id", 1), ("status", 1)])
        self.feedback.create_index([("lead_id", 1), ("occurred_at", -1)])

    # -- app metadata (e.g. last crawl time; survives free-tier restarts) ---
    def get_meta(self, key: str):
        doc = self._db["meta"].find_one({"_id": key})
        return doc.get("value") if doc else None

    def set_meta(self, key: str, value) -> None:
        self._db["meta"].update_one({"_id": key}, {"$set": {"value": value}}, upsert=True)

    # -- write (used by the export script / Phase-2 crawl) ------------------
    def upsert_lead(self, organization_id: str, detail: dict) -> None:
        doc = dict(detail)
        doc["_id"] = detail["id"]
        doc["organization_id"] = organization_id
        doc["event_date"] = _to_dt((detail.get("event") or {}).get("date"))
        self.leads.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    # -- repository protocol ------------------------------------------------
    def list_leads(self, organization_id: str, filters: dict) -> list[dict]:
        q: dict = {"organization_id": organization_id}
        if filters.get("score_min"):
            q["score"] = {"$gte": int(filters["score_min"])}
        if filters.get("sector"):
            q["event.sector"] = filters["sector"]
        if filters.get("product"):
            q["opportunity"] = filters["product"]
        if filters.get("event_type"):
            q["event.type_label"] = filters["event_type"]
        if filters.get("gov_org"):
            q["event.org"] = filters["gov_org"]
        if filters.get("status"):
            q["status"] = filters["status"]
        if filters.get("company"):
            q["company"] = {"$regex": re.escape(filters["company"]), "$options": "i"}
        if filters.get("date_days"):
            since = datetime.now(timezone.utc) - timedelta(days=int(filters["date_days"]))
            q["event_date"] = {"$gte": since}  # excludes undated (null) leads
        projection = {"_id": 0, **{k: 1 for k in _SUMMARY_KEYS}}
        # Newest first by award date; undated (null) sort last in a descending sort;
        # score breaks ties.
        cursor = self.leads.find(q, projection).sort([("event_date", -1), ("score", -1)])
        return list(cursor)

    def get_lead(self, organization_id: str, lead_id: str) -> dict | None:
        return self.leads.find_one(
            {"_id": lead_id, "organization_id": organization_id},
            {"_id": 0, "organization_id": 0, "event_date": 0, "feedback": 0},
        )

    def record_feedback(self, organization_id: str, lead_id: str,
                        event_type: FeedbackEventType, note: str | None, actor: str) -> dict:
        doc = self.leads.find_one(
            {"_id": lead_id, "organization_id": organization_id}, {"score": 1, "status": 1})
        if doc is None:
            return {"ok": False, "reason": "not_found"}
        self.feedback.insert_one({
            "lead_id": lead_id, "organization_id": organization_id,
            "event_type": getattr(event_type, "value", str(event_type)),
            "note": note, "actor": actor, "occurred_at": datetime.now(timezone.utc),
            "score_at_event": doc.get("score"),
        })
        new_status = _STATUS_BY_EVENT.get(event_type)
        if new_status:
            self.leads.update_one({"_id": lead_id}, {"$set": {"status": new_status}})
        return {"ok": True, "status": new_status or doc.get("status")}


# --------------------------------------------------------------------------- #
# Change-stream watcher → WebSocket push (parallels app.api.ws.db_listener)
# --------------------------------------------------------------------------- #
def _watch_blocking(repo: MongoLeadRepository, manager, loop: asyncio.AbstractEventLoop,
                    stop: threading.Event) -> None:
    try:
        repo.ensure_indexes()
    except Exception as exc:  # noqa: BLE001 - indexes are best-effort at startup
        logger.warning('{"event": "mongo_index_error", "detail": "%s"}', exc)
    while not stop.is_set():
        try:
            with repo.leads.watch(max_await_time_ms=1000) as stream:
                logger.info('{"event": "mongo_watch_ready"}')
                while not stop.is_set():
                    change = stream.try_next()
                    if change is not None:
                        asyncio.run_coroutine_threadsafe(
                            manager.broadcast({"type": "leads_changed"}), loop)
        except Exception as exc:  # noqa: BLE001 - keep the watcher alive (reconnect)
            if stop.is_set():
                return
            logger.warning('{"event": "mongo_watch_error", "detail": "%s"}', exc)
            stop.wait(3)


async def mongo_change_listener(app) -> None:
    """Start the change-stream watcher thread; keep it alive until cancelled."""
    loop = asyncio.get_running_loop()
    stop = threading.Event()
    thread = threading.Thread(
        target=_watch_blocking, args=(app.state.repository, app.state.ws_manager, loop, stop),
        name="mongo-change-watcher", daemon=True,
    )
    thread.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        stop.set()
        raise
