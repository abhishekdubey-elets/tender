"""LLM crawl extraction: mapping, junk filtering, and the provider chain."""
import json
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.crawl.llm_extract import extract_llm, extract_llm_openai
from app.extraction.llm import FakeLLMClient, LLMError


class FakeOpenAI:
    """Minimal stand-in for openai.OpenAI: chat.completions.create."""

    def __init__(self, payload=None, exc: Exception | None = None):
        self.calls: list[dict] = []

        def create(**kwargs):
            self.calls.append(kwargs)
            if exc is not None:
                raise exc
            msg = SimpleNamespace(content=json.dumps(payload), refusal=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

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


def test_openai_extraction_maps_and_calls_with_schema():
    fake = FakeOpenAI({"leads": [
        {"index": 0, "company": "TCS", "government_buyer": "MeitY", "amount": "₹500 crore"}]})
    leads = extract_llm_openai(BY_SECTOR, Settings(openai_api_key="k"), client=fake)
    assert [l["company"] for l in leads] == ["TCS"]
    call = fake.calls[0]
    assert call["response_format"]["json_schema"]["strict"] is True
    assert call["messages"][0]["role"] == "system"


def test_openai_error_raises_llm_error():
    fake = FakeOpenAI(exc=RuntimeError("quota"))
    with pytest.raises(LLMError):
        extract_llm_openai(BY_SECTOR, Settings(openai_api_key="k"), client=fake)


def _crawl_with(monkeypatch, env: dict, openai_fn=None, anthropic_fn=None):
    from app.crawl import service

    monkeypatch.setattr(service, "fetch_candidates", lambda per_vertical=10: {
        "e-Governance": [{"title": "TCS wins ₹500 crore contract from Ministry of Electronics & IT",
                          "source": "PTI", "date": None}]})
    monkeypatch.setattr(service, "persist_leads", lambda leads, session_factory=None: [])
    import app.config as config
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    if openai_fn is not None:
        monkeypatch.setattr("app.crawl.llm_extract.extract_llm_openai", openai_fn)
    if anthropic_fn is not None:
        monkeypatch.setattr("app.crawl.llm_extract.extract_llm", anthropic_fn)
    config.get_settings.cache_clear()
    try:
        return service.run_crawl(session_factory=object)
    finally:
        config.get_settings.cache_clear()


FAKE_LEAD = {"company": "TCS", "vertical": "e-Governance", "government_buyer": "MeitY",
             "amount": None, "what_won": "t", "source": "PTI", "date": None,
             "confidence": 0.65, "reason_to_call": "call"}


def test_run_crawl_prefers_openai_when_both_keys_set(monkeypatch):
    report = _crawl_with(monkeypatch, {"OPENAI_API_KEY": "k1", "ANTHROPIC_API_KEY": "k2"},
                         openai_fn=lambda *a, **k: [FAKE_LEAD],
                         anthropic_fn=lambda *a, **k: pytest.fail("anthropic must not run"))
    assert report.extraction == "openai"


def test_run_crawl_falls_back_openai_to_anthropic(monkeypatch):
    def boom(*a, **k):
        raise LLMError("openai down")
    report = _crawl_with(monkeypatch, {"OPENAI_API_KEY": "k1", "ANTHROPIC_API_KEY": "k2"},
                         openai_fn=boom, anthropic_fn=lambda *a, **k: [FAKE_LEAD])
    assert report.extraction == "anthropic"


def test_run_crawl_falls_back_to_rules_when_all_llms_fail(monkeypatch):
    def boom(*a, **k):
        raise LLMError("down")
    report = _crawl_with(monkeypatch, {"OPENAI_API_KEY": "k1", "ANTHROPIC_API_KEY": "k2"},
                         openai_fn=boom, anthropic_fn=boom)
    assert report.extraction == "rules"
    assert report.extracted == 1
