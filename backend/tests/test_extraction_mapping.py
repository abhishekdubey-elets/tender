"""Mapping extracted events → government_events / event_sources ORM (no DB)."""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.db.enums import EventType
from app.db.models import RawDocument
from app.extraction.llm import FakeLLMClient
from app.extraction.mapping import map_event_type, normalize_currency, to_orm
from app.extraction.service import EventExtractionService
from tests.ext_util import envelope, event, fixed_now, make_norm

DOC = (
    "The Ministry of Ports has awarded a contract worth INR 50000000 to "
    "Acme Infra Pvt Ltd for the Port Automation project on 2026-08-01."
)


def _result():
    resp = envelope(event(
        event_type="contract_award",
        government_entity="Ministry of Ports",
        entities=[{"name": "Acme Infra Pvt Ltd", "role": "awardee"}],
        contract_value=50000000, currency="Rupees", project="Port Automation",
        award_date="2026-08-01", location="Gujarat",
        evidence=[{"field": "entities[0].name", "snippet": "Acme Infra Pvt Ltd"}],
        confidence=0.9,
    ))
    svc = EventExtractionService(FakeLLMClient([resp]), now=fixed_now)
    return svc.extract(make_norm(DOC))


def _raw() -> RawDocument:
    raw = RawDocument(
        government_source_id=uuid.uuid4(),
        source_url="https://pib.gov.in/pr/1",
        content_hash="hash1",
    )
    raw.id = uuid.uuid4()
    return raw


def test_map_event_type_and_currency() -> None:
    assert map_event_type("contract_award") is EventType.award
    assert map_event_type("scheme") is EventType.other
    assert map_event_type("work_order") is EventType.work_order
    assert normalize_currency("Rupees") == "INR"
    assert normalize_currency("₹") == "INR"
    assert normalize_currency(None) is None


def test_to_orm_builds_event_and_evidence() -> None:
    result = _result()
    raw = _raw()
    pairs = to_orm(result, raw)
    assert len(pairs) == 1
    ge, es = pairs[0]

    # government_events fields
    assert ge.event_type is EventType.award            # contract_award → award
    assert ge.value_amount == Decimal("50000000")
    assert ge.currency == "INR"                        # normalized from "Rupees"
    assert ge.buyer_name == "Ministry of Ports"
    assert ge.awardee_name == "Acme Infra Pvt Ltd"
    assert str(ge.event_date) == "2026-08-01"
    assert ge.dedup_key
    assert ge.attributes["extraction_event_type"] == "contract_award"
    assert ge.attributes["entities"][0]["name"] == "Acme Infra Pvt Ltd"

    # event_sources (provenance/evidence)
    assert es.event is ge
    assert es.raw_document_id == raw.id
    assert es.government_source_id == raw.government_source_id
    assert es.source_url == "https://pib.gov.in/pr/1"
    assert es.extraction_model == result.meta.model
    assert es.is_primary is True
    assert "Acme Infra Pvt Ltd" in es.snippet
    assert es.extracted_payload["entities"][0]["name"] == "Acme Infra Pvt Ltd"
