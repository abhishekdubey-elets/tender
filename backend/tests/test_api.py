"""Read-API tests: auth, authorization, validation, rate limiting, feedback."""
from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")
from fastapi.testclient import TestClient  # noqa: E402

from app.api import create_app  # noqa: E402
from app.api.repository import InMemoryLeadRepository  # noqa: E402
from app.config import Settings  # noqa: E402

KEY1, KEY2, VIEWER = "key-org1-analyst", "key-org2-analyst", "key-org1-viewer"


def _lead(id_, org):
    return {"id": id_, "organization_id": org, "company": "Acme Defence", "status": "new",
            "event": {"type": "contract_award", "type_label": "Contract award", "title": "Surveillance",
                      "value": 5e8, "org": "Ministry of Defence", "sector": "Defence", "date": "2026-08-18"},
            "opportunity": "Cybersecurity Services", "opportunity_tier": "inference", "score": 91,
            "grade": "A", "confidence": 0.88, "why_now": "recent", "reason_to_call": "fit",
            "target_contact": "CISO", "company_profile": {}, "opportunity_detail": {}, "evidence": [],
            "score_components": [], "contact": None, "brief": [], "risk": None, "sources": []}


def _client(rate=120):
    repo = InMemoryLeadRepository()
    repo.add(_lead("L1", "org-1"))
    repo.add(_lead("L2", "org-2"))
    settings = Settings(api_keys={KEY1: "org-1:analyst", KEY2: "org-2:analyst", VIEWER: "org-1:viewer"},
                        rate_limit_per_minute=rate)
    return TestClient(create_app(settings, repository=repo)), repo


def h(key):
    return {"X-API-Key": key}


def test_auth_required_and_validated():
    c, _ = _client()
    assert c.get("/api/leads").status_code == 401
    assert c.get("/api/leads", headers=h("wrong")).status_code == 401
    r = c.get("/api/leads", headers=h(KEY1))
    assert r.status_code == 200 and r.headers["X-Content-Type-Options"] == "nosniff"


def test_org_scoping_and_no_cross_tenant_leak():
    c, _ = _client()
    assert [l["id"] for l in c.get("/api/leads", headers=h(KEY1)).json()] == ["L1"]
    assert [l["id"] for l in c.get("/api/leads", headers=h(KEY2)).json()] == ["L2"]
    # org-1 cannot read org-2's lead — 404, not 403 (no existence leak)
    assert c.get("/api/leads/L2", headers=h(KEY1)).status_code == 404


def test_query_validation():
    c, _ = _client()
    assert c.get("/api/leads?score_min=200", headers=h(KEY1)).status_code == 422
    assert c.get("/api/leads?score_min=80", headers=h(KEY1)).status_code == 200


def test_filters_apply():
    c, _ = _client()
    assert len(c.get("/api/leads?score_min=95", headers=h(KEY1)).json()) == 0
    assert len(c.get("/api/leads?sector=Defence", headers=h(KEY1)).json()) == 1
    assert len(c.get("/api/leads?company=zzz", headers=h(KEY1)).json()) == 0


def test_feedback_requires_role_and_updates_status():
    c, repo = _client()
    # viewer role cannot write feedback
    assert c.post("/api/leads/L1/feedback", headers=h(VIEWER),
                  json={"event_type": "meeting_booked"}).status_code == 403
    # analyst can, and status advances
    r = c.post("/api/leads/L1/feedback", headers=h(KEY1), json={"event_type": "meeting_booked"})
    assert r.status_code == 200 and r.json()["status"] == "meeting"
    assert len(repo.feedback) == 1
    # invalid event type rejected
    assert c.post("/api/leads/L1/feedback", headers=h(KEY1),
                  json={"event_type": "nonsense"}).status_code == 422
    # feedback on someone else's lead → 404
    assert c.post("/api/leads/L2/feedback", headers=h(KEY1),
                  json={"event_type": "contacted"}).status_code == 404


def test_rate_limiting_returns_429():
    c, _ = _client(rate=3)
    codes = [c.get("/api/leads", headers=h(KEY1)).status_code for _ in range(5)]
    assert codes.count(200) == 3 and codes.count(429) == 2
    last = c.get("/api/leads", headers=h(KEY1))
    assert last.status_code == 429 and "Retry-After" in last.headers
