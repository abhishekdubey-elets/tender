"""LLM crawl extraction: mapping, junk filtering, and rule fallback."""
import pytest

from app.config import Settings
from app.crawl.llm_extract import extract_llm
from app.extraction.llm import FakeLLMClient, LLMError

BY_SECTOR = {
    "e-Governance": [
        {"title": "TCS wins ₹500 crore e-gov deal from MeitY", "source": "PTI", "date": "2026-08-26"},
        {"title": "We win big: mystery firm bags order", "source": "Blog", "date": None},
    ],
    "Banking": [
        {"title": "Infosys signs core-banking deal with SBI", "source": "Mint", "date": "2026-08-25"},
    ],
}


def _settings() -> Settings:
    return Settings(anthropic_api_key="test-key")


def test_maps_model_output_to_lead_shape():
    llm = FakeLLMClient([{"leads": [
        {"index": 0, "company": "TCS", "government_buyer": "MeitY", "amount": "₹500 crore"},
        {"index": 2, "company": "Infosys", "government_buyer": "State Bank of India", "amount": None},
    ]}])
    leads = extract_llm(BY_SECTOR, _settings(), llm=llm)
    assert [(l["company"], l["vertical"]) for l in leads] == [
        ("TCS", "e-Governance"), ("Infosys", "Banking")]
    assert leads[0]["amount"] == "₹500 crore"
    assert leads[1]["amount"] is None
    assert leads[1]["government_buyer"] == "State Bank of India"
    assert "TCS" in leads[0]["reason_to_call"]


def test_filters_junk_names_bad_indices_and_duplicates():
    llm = FakeLLMClient([{"leads": [
        {"index": 1, "company": "We", "government_buyer": "x", "amount": None},
        {"index": 99, "company": "Ghost Corp", "government_buyer": "x", "amount": None},
        {"index": 0, "company": "TCS", "government_buyer": "MeitY", "amount": None},
        {"index": 2, "company": "tcs", "government_buyer": "SBI", "amount": None},
    ]}])
    leads = extract_llm(BY_SECTOR, _settings(), llm=llm)
    assert [l["company"] for l in leads] == ["TCS"]


def test_empty_input_makes_no_llm_call():
    llm = FakeLLMClient([])
    assert extract_llm({}, _settings(), llm=llm) == []
    assert llm.calls == []


def test_llm_error_propagates_for_caller_fallback():
    llm = FakeLLMClient([LLMError("api down")])
    with pytest.raises(LLMError):
        extract_llm(BY_SECTOR, _settings(), llm=llm)


def test_run_crawl_falls_back_to_rules_on_llm_failure(monkeypatch):
    from app.crawl import service

    monkeypatch.setattr(service, "fetch_candidates", lambda per_vertical=10: {
        "e-Governance": [{"title": "TCS wins ₹500 crore contract from Ministry of Electronics & IT",
                          "source": "PTI", "date": None}]})
    monkeypatch.setattr(service, "persist_leads", lambda leads, session_factory=None: [])
    import app.config as config
    config.get_settings.cache_clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "bad-key-forces-llm-path")
    monkeypatch.setattr("app.crawl.llm_extract.extract_llm",
                        lambda *a, **k: (_ for _ in ()).throw(LLMError("boom")))
    try:
        report = service.run_crawl(session_factory=object)
    finally:
        config.get_settings.cache_clear()
    assert report.extraction == "rules"
    assert report.extracted == 1
