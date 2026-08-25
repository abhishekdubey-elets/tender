"""EventExtractionService tests — the seven required scenarios plus retry,
validation, grounding, caching and determinism handling. Uses a scripted fake
LLM (no API key / network)."""
from __future__ import annotations

from app.extraction.llm import FakeLLMClient, LLMError
from app.extraction.service import EventExtractionService
from app.extraction.types import ExtractionStatus
from tests.ext_util import envelope, event, fixed_now, make_norm


def _svc(responses, **kw) -> tuple[EventExtractionService, FakeLLMClient]:
    llm = FakeLLMClient(responses)
    return EventExtractionService(llm, now=fixed_now, **kw), llm


# --- 1. Clean government announcement ---------------------------------------
CLEAN = (
    "The Ministry of Housing and Urban Affairs has awarded a contract worth "
    "INR 50000000 to Acme Infra Pvt Ltd for the Smart City Command Centre "
    "project in Pune on 2026-08-01."
)


def test_clean_announcement() -> None:
    resp = envelope(event(
        event_type="contract_award",
        government_entity="Ministry of Housing and Urban Affairs",
        entities=[{"name": "Acme Infra Pvt Ltd", "role": "awardee"}],
        contract_value=50000000, currency="INR", sector="Urban",
        project="Smart City Command Centre", award_date="2026-08-01", location="Pune",
        description="Contract awarded for the Smart City Command Centre.",
        evidence=[
            {"field": "government_entity", "snippet": "Ministry of Housing and Urban Affairs"},
            {"field": "contract_value", "snippet": "contract worth INR 50000000"},
            {"field": "entities[0].name", "snippet": "Acme Infra Pvt Ltd"},
        ],
        confidence=0.9,
    ))
    svc, llm = _svc([resp])
    result = svc.extract(make_norm(CLEAN))

    assert result.status is ExtractionStatus.succeeded
    assert len(result.events) == 1
    ev = result.events[0]
    assert ev.event_type == "contract_award"
    assert ev.entities[0].name == "Acme Infra Pvt Ltd"
    assert ev.contract_value == 50000000
    assert str(ev.award_date) == "2026-08-01"
    assert result.warnings == []
    # provenance: model/provider/version + timestamps recorded
    assert result.meta.provider == "anthropic"
    assert result.meta.model == "claude-opus-5"   # actual model used is recorded
    assert result.meta.prompt_version
    assert result.meta.requested_at == fixed_now()
    assert result.meta.completed_at is not None
    assert result.meta.attempts == 1


# --- 2. Ambiguous document ---------------------------------------------------
def test_ambiguous_document_yields_unknowns_and_low_confidence() -> None:
    doc = "The department reviewed various ongoing initiatives during the meeting."
    resp = envelope(event(event_type="other", confidence=0.3))
    svc, _ = _svc([resp])
    result = svc.extract(make_norm(doc))
    ev = result.events[0]
    assert ev.event_type == "other"
    assert ev.contract_value is None       # never invented
    assert ev.entities == []
    assert ev.confidence <= 0.5


# --- 3. Missing company ------------------------------------------------------
def test_missing_company_entities_empty() -> None:
    doc = "INR 20 lakh has been sanctioned under the rural roads scheme."
    resp = envelope(event(
        event_type="funding", contract_value=2000000, currency="INR",
        evidence=[{"field": "contract_value", "snippet": "INR 20 lakh"}], confidence=0.7,
    ))
    svc, _ = _svc([resp])
    ev = svc.extract(make_norm(doc)).events[0]
    assert ev.entities == []
    assert ev.contract_value == 2000000


# --- 4. Missing contract value ----------------------------------------------
def test_missing_contract_value_is_null() -> None:
    doc = "A work order has been issued to Beta Ltd for the road resurfacing works."
    resp = envelope(event(
        event_type="work_order",
        entities=[{"name": "Beta Ltd", "role": "awardee"}],
        evidence=[{"field": "entities[0].name", "snippet": "Beta Ltd"}], confidence=0.75,
    ))
    svc, _ = _svc([resp])
    ev = svc.extract(make_norm(doc)).events[0]
    assert ev.contract_value is None
    assert ev.currency is None
    assert ev.entities[0].name == "Beta Ltd"


# --- 5. Multiple companies (one event, several entities) --------------------
def test_multiple_companies_in_one_event() -> None:
    doc = "A consortium of Acme Ltd and Beta Ltd was awarded the metro rail contract."
    resp = envelope(event(
        event_type="contract_award",
        entities=[
            {"name": "Acme Ltd", "role": "partner"},
            {"name": "Beta Ltd", "role": "partner"},
        ],
        evidence=[
            {"field": "entities[0].name", "snippet": "Acme Ltd"},
            {"field": "entities[1].name", "snippet": "Beta Ltd"},
        ],
        confidence=0.8,
    ))
    svc, _ = _svc([resp])
    ev = svc.extract(make_norm(doc)).events[0]
    assert [e.name for e in ev.entities] == ["Acme Ltd", "Beta Ltd"]


# --- 6. Multiple contracts (several events) ---------------------------------
def test_multiple_contracts_yield_multiple_events() -> None:
    doc = (
        "Acme Ltd won a contract for water works; separately, Beta Ltd received a "
        "work order for street lighting."
    )
    resp = envelope(
        event(event_type="contract_award",
              entities=[{"name": "Acme Ltd", "role": "awardee"}],
              evidence=[{"field": "entities[0].name", "snippet": "Acme Ltd"}], confidence=0.8),
        event(event_type="work_order",
              entities=[{"name": "Beta Ltd", "role": "awardee"}],
              evidence=[{"field": "entities[0].name", "snippet": "Beta Ltd"}], confidence=0.8),
    )
    svc, _ = _svc([resp])
    result = svc.extract(make_norm(doc))
    assert len(result.events) == 2
    assert {e.event_type for e in result.events} == {"contract_award", "work_order"}


# --- 7. Duplicate information (same event twice → identical dedup key) -------
def test_duplicate_information_produces_identical_dedup_key() -> None:
    from app.extraction.mapping import compute_dedup_key

    doc = (
        "Acme Infra Pvt Ltd was awarded INR 50000000. In related news, "
        "Acme Infra Pvt Ltd was awarded INR 50000000."
    )
    dup = event(
        event_type="contract_award",
        entities=[{"name": "Acme Infra Pvt Ltd", "role": "awardee"}],
        contract_value=50000000, award_date="2026-08-01",
        evidence=[{"field": "entities[0].name", "snippet": "Acme Infra Pvt Ltd"}], confidence=0.85,
    )
    svc, _ = _svc([envelope(dup, dict(dup))])
    result = svc.extract(make_norm(doc))
    assert len(result.events) == 2
    keys = {compute_dedup_key(e) for e in result.events}
    assert len(keys) == 1   # duplicates collapse to one dedup key


# --- retry / validation / grounding -----------------------------------------
def test_retries_on_schema_validation_then_succeeds() -> None:
    bad = envelope(event(confidence=5.0))                 # confidence out of range
    good = envelope(event(event_type="policy", confidence=0.6))
    svc, llm = _svc([bad, good])
    result = svc.extract(make_norm("A new policy was notified."))
    assert result.status is ExtractionStatus.succeeded
    assert result.meta.attempts == 2
    assert len(llm.calls) == 2


def test_retries_on_transport_error() -> None:
    good = envelope(event(event_type="policy", confidence=0.6))
    svc, llm = _svc([LLMError("network down"), good])
    result = svc.extract(make_norm("A new policy was notified."))
    assert result.status is ExtractionStatus.succeeded
    assert result.meta.attempts == 2


def test_ungrounded_evidence_stripped_when_retries_exhausted() -> None:
    resp = envelope(event(
        event_type="policy",
        evidence=[{"field": "description", "snippet": "THIS PHRASE IS NOT IN THE DOCUMENT"}],
        confidence=0.6,
    ))
    svc, _ = _svc([resp], max_attempts=1)
    result = svc.extract(make_norm("A new policy was notified today."))
    assert result.status is ExtractionStatus.succeeded
    assert result.events[0].evidence == []            # ungrounded snippet removed
    assert any("ungrounded" in w for w in result.warnings)


def test_ungrounded_then_grounded_on_retry() -> None:
    doc = "Beta Ltd received a work order."
    bad = envelope(event(event_type="work_order",
                         evidence=[{"field": "x", "snippet": "not present"}], confidence=0.6))
    good = envelope(event(event_type="work_order",
                          evidence=[{"field": "entities", "snippet": "Beta Ltd received a work order"}],
                          confidence=0.6))
    svc, _ = _svc([bad, good], max_attempts=2)
    result = svc.extract(make_norm(doc))
    assert result.status is ExtractionStatus.succeeded
    assert result.meta.attempts == 2
    assert result.warnings == []


def test_failure_after_exhausting_retries() -> None:
    bad = envelope(event(confidence=9.0))
    svc, _ = _svc([bad, bad, bad], max_attempts=3)
    result = svc.extract(make_norm("something"))
    assert result.status is ExtractionStatus.failed
    assert "schema_validation" in result.error
    assert result.events == []


# --- caching / determinism / skip -------------------------------------------
def test_cache_reused_for_identical_input() -> None:
    resp = envelope(event(event_type="policy", confidence=0.6))
    cache: dict = {}
    llm = FakeLLMClient([resp])
    svc = EventExtractionService(llm, now=fixed_now, cache=cache)
    doc = make_norm("A new policy was notified.")

    first = svc.extract(doc)
    second = svc.extract(doc)
    assert first.status is ExtractionStatus.succeeded
    assert second.meta.from_cache is True
    assert len(llm.calls) == 1                # LLM only called once
    assert [e.event_type for e in second.events] == [e.event_type for e in first.events]


def test_empty_text_is_skipped_without_calling_llm() -> None:
    llm = FakeLLMClient([])
    svc = EventExtractionService(llm, now=fixed_now)
    result = svc.extract(make_norm("   "))
    assert result.status is ExtractionStatus.skipped
    assert llm.calls == []
