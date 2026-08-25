"""AI Sales Brief generator: grounding, fact/inference split, invention flagging."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.brief import BriefInput, ContactInfo, SalesBriefGenerator
from app.brief.facts import build_factbook
from app.brief.llm import FakeBriefLLM
from app.brief.verify import find_unsupported_contacts, find_unsupported_numbers
from app.enrichment.types import Claim, EnrichmentField, EnrichmentResult, FieldResult, SourceTier
from app.opportunity.types import EpistemicTier, EventInput, Evidence, Opportunity
from app.scoring.types import LeadScore, ScoreComponent

NOW = datetime(2026, 8, 25, tzinfo=timezone.utc)


def _event() -> EventInput:
    ev = Evidence(EpistemicTier.fact, "Acme Defence Ltd won a defence surveillance contract",
                  "event", "https://pib.gov.in/pr/1", "awarded a contract", 0.9)
    return EventInput(
        event_type="contract_award", value_amount=5e8, currency="INR", sector="Defence",
        buyer="Ministry of Defence", awardee="Acme Defence Ltd", event_date=date(2026, 8, 20),
        title="Defence surveillance contract", description="Surveillance systems.", evidence=[ev],
    )


def _opportunity() -> Opportunity:
    ev = Evidence(EpistemicTier.fact, "Acme Defence Ltd won a defence surveillance contract",
                  "event", "https://pib.gov.in/pr/1", "awarded a contract", 0.9)
    return Opportunity(
        product_id="cyber-1", product_name="Cybersecurity Services", category="cybersecurity",
        need_key="security_requirements", need_hypothesis="Cybersecurity & data-protection need",
        trigger="contract award in Defence", reasoning="Sensitive defence data suggests a security need.",
        epistemic_tier=EpistemicTier.inference, confidence=0.8, timing="0-6 months",
        supporting_evidence=[ev], assumptions=["assumes sensitive data is handled"],
        alternative_explanations=["may rely on an in-house security team"],
        departments=["IT Security"], job_titles=["CISO", "CIO"],
    )


def _enrichment(known: bool = True) -> EnrichmentResult:
    profile = {f: FieldResult(f, None, 0.0, "unknown", []) for f in EnrichmentField}
    if known:
        def claim(field, value, url):
            return Claim(field, value, "registry", url, SourceTier.authoritative, NOW, "evidence", 0.9)
        profile[EnrichmentField.industry] = FieldResult(
            EnrichmentField.industry, "Defence Manufacturing", 0.9, "known",
            [claim(EnrichmentField.industry, "Defence Manufacturing", "https://mca.gov.in/acme")])
        profile[EnrichmentField.hq_location] = FieldResult(
            EnrichmentField.hq_location, "Pune, Maharashtra", 0.9, "known",
            [claim(EnrichmentField.hq_location, "Pune, Maharashtra", "https://mca.gov.in/acme")])
        profile[EnrichmentField.funding_signals] = FieldResult(
            EnrichmentField.funding_signals,
            [{"value": "Acme raised Series B", "source_url": "https://news/f",
              "retrieved_at": NOW.isoformat(), "evidence": "raised", "confidence": 0.65}],
            0.65, "known",
            [claim(EnrichmentField.funding_signals, "Acme raised Series B", "https://news/f")])
    return EnrichmentResult(company_ref=None, profile=profile, generated_at=NOW)


def _score() -> LeadScore:
    return LeadScore(total=88, grade="A",
                     components=[ScoreComponent("sector_relevance", "Sector relevance", 25, 25, "match")],
                     config_version="lead-score-v1", scored_at=NOW)


def _input(*, contact=None, enrichment=True, score=True) -> BriefInput:
    return BriefInput(
        event=_event(), company_name="Acme Defence Ltd", opportunity=_opportunity(),
        enrichment=_enrichment(enrichment) if enrichment else None,
        score=_score() if score else None, contact=contact,
    )


GEN = SalesBriefGenerator(now=lambda: NOW)


# --- deterministic grounding -------------------------------------------------
def test_deterministic_brief_is_grounded_and_complete() -> None:
    brief = GEN.generate(_input())
    assert brief.status == "ok" and brief.flags == []
    # all ten sections present
    assert set(brief.sections) >= {
        "trigger", "why_this_company", "why_now", "business_need", "who_to_contact",
        "reason_to_call", "evidence", "confidence", "recommended_next_action", "risk",
    }
    # facts vs inference are distinguished
    assert brief.sections["trigger"].is_inference is False
    assert brief.sections["business_need"].is_inference is True
    assert brief.sections["risk"].is_inference is True
    # verified facts are all FACT-tier and the evidence section references them
    assert brief.verified_facts and all(f.is_verified for f in brief.verified_facts)
    assert "[F1]" in brief.sections["evidence"].text
    # the trigger cites event facts (traceable)
    assert brief.sections["trigger"].relies_on
    assert brief.meta.mode == "deterministic" and brief.meta.prompt_version


def test_does_not_invent_when_data_is_sparse() -> None:
    brief = GEN.generate(_input(enrichment=False, score=False, contact=None))
    assert "Limited verified public data" in brief.sections["why_this_company"].text
    assert "No specific contact verified" in brief.sections["who_to_contact"].text
    assert "No verified decision-maker contact" in brief.sections["risk"].text
    # nothing fabricated
    assert brief.status == "ok"


# --- verification units ------------------------------------------------------
def test_verify_flags_unsupported_number_but_allows_real_one() -> None:
    fb = build_factbook(_input())
    assert find_unsupported_numbers("value is ₹50.0 cr", fb) == []       # real value
    assert "999cr" in find_unsupported_numbers("also a ₹999 crore deal", fb)


def test_verify_flags_invented_email() -> None:
    fb = build_factbook(_input(contact=None))
    assert "ceo@acme.com" in find_unsupported_contacts("email ceo@acme.com", fb)


# --- LLM invention is flagged & replaced ------------------------------------
def test_llm_invented_number_is_flagged_and_replaced() -> None:
    llm = FakeBriefLLM(handler=lambda user, n: {
        "why_now": {"text": "Very timely — Acme also won a ₹999 crore side deal.", "fact_ids": []},
    })
    brief = GEN.generate(_input(), llm=llm)
    assert brief.status == "flagged"
    assert any("why_now" in f for f in brief.flags)
    # the invented figure never reaches the output
    assert "999" not in brief.render()
    # the section fell back to grounded deterministic text
    assert "999" not in brief.sections["why_now"].text


def test_llm_invented_contact_is_flagged() -> None:
    llm = FakeBriefLLM(handler=lambda user, n: {
        "reason_to_call": {"text": "Email the CISO at ceo@acme.com to set up a call.", "fact_ids": []},
    })
    brief = GEN.generate(_input(contact=None), llm=llm)
    assert brief.status == "flagged"
    assert "ceo@acme.com" not in brief.render()


def test_llm_clean_rewrite_is_accepted() -> None:
    llm = FakeBriefLLM(handler=lambda user, n: {
        "why_this_company": {"text": "A defence manufacturer, a strong ICP fit.", "fact_ids": []},
    })
    brief = GEN.generate(_input(), llm=llm)
    assert brief.status == "ok" and brief.flags == []
    assert brief.sections["why_this_company"].text == "A defence manufacturer, a strong ICP fit."
    assert brief.meta.mode == "llm" and brief.meta.model == "fake-brief-model"


# --- verified contact flows through -----------------------------------------
def test_verified_contact_is_used_without_invention() -> None:
    contact = ContactInfo(name="Priya Rao", title="CISO", seniority="c_level",
                          email="priya@acmedefence.com", source_url="https://linkedin/priya",
                          confidence=0.8, verified=True)
    brief = GEN.generate(_input(contact=contact))
    assert "Priya Rao" in brief.sections["who_to_contact"].text
    assert brief.sections["who_to_contact"].is_inference is False
