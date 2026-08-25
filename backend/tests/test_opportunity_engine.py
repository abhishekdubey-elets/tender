"""Opportunity Detection Engine tests across multiple product categories."""
from __future__ import annotations

from datetime import date

from app.opportunity import (
    CompanyProfileInput,
    EpistemicTier,
    EventInput,
    Evidence,
    OpportunityEngine,
    ProductInput,
    SignalInfo,
    TargetProfile,
)
from app.opportunity.engine import ReasonerNote
from app.opportunity.knowledge_base import KnowledgeBase


def ev_fact(stmt="Acme won a government contract", url="https://pib.gov.in/pr/1") -> Evidence:
    return Evidence(EpistemicTier.fact, stmt, "event", url, "verbatim snippet", 0.9)


def event(**kw) -> EventInput:
    base = dict(
        event_type="contract_award", value_amount=5e8, currency="INR",
        awardee="Acme Ltd", event_date=date(2026, 8, 1), evidence=[ev_fact()],
    )
    base.update(kw)
    return EventInput(**base)


def company(signals=None, **kw) -> CompanyProfileInput:
    return CompanyProfileInput(name=kw.pop("name", "Acme Ltd"), signals=signals or {}, **kw)


def signal(name, value="yes", conf=0.7) -> SignalInfo:
    return SignalInfo(name=name, present=True, value=value, confidence=conf,
                      source_url="https://news/x", evidence="reported")


def product(category, pid=None, name=None) -> ProductInput:
    return ProductInput(product_id=pid or category, name=name or category, category=category)


ENGINE = OpportunityEngine()


# --- multiple categories -----------------------------------------------------
def test_defence_contract_creates_cyber_and_workforce_opportunities() -> None:
    e = event(sector="Defence", title="Defence surveillance systems contract", awardee="Acme Defence Ltd")
    c = company(name="Acme Defence Ltd", industry="Defence")
    t = TargetProfile(sectors=["Defence"])
    bundle = ENGINE.detect(e, c, t, [product("cybersecurity"), product("workforce_staffing")])

    cats = {o.category for o in bundle.opportunities}
    assert "cybersecurity" in cats
    assert "workforce_staffing" in cats
    # these are hypotheses, not facts
    assert all(o.epistemic_tier is not EpistemicTier.fact for o in bundle.opportunities)
    # each opportunity is grounded by the event fact
    for o in bundle.opportunities:
        assert any(ev.kind == "event" for ev in o.supporting_evidence)
        assert o.trigger and o.reasoning and o.timing and o.assumptions and o.alternative_explanations


def test_digital_infrastructure_contract_creates_cloud_opportunity() -> None:
    e = event(value_amount=2e8, sector="e-Governance",
              title="Digital infrastructure and cloud platform rollout")
    bundle = ENGINE.detect(e, company(industry="IT"), TargetProfile(sectors=["e-Governance"]),
                           [product("cloud_infrastructure")])
    assert [o.category for o in bundle.opportunities] == ["cloud_infrastructure"]
    assert bundle.opportunities[0].need_key == "infrastructure_expansion"


# --- FACT / INFERENCE / SPECULATION separation ------------------------------
def test_facts_inferences_and_speculations_are_separated() -> None:
    e = event(value_amount=2e8, sector="Smart Cities",
              title="Smart city digital infrastructure mission")
    bundle = ENGINE.detect(
        e, company(industry="Smart Cities"), TargetProfile(sectors=["Smart Cities"]),
        [product("cloud_infrastructure"), product("events_sponsorship")],
    )
    # FACTS are grounded inputs, not opportunities.
    assert bundle.facts and all(f.tier is EpistemicTier.fact for f in bundle.facts)
    # cloud → inference, events_sponsorship (no corroborating signal) → speculation.
    assert any(o.category == "cloud_infrastructure" for o in bundle.inferences)
    assert any(o.category == "events_sponsorship" for o in bundle.speculations)
    # partition is clean
    inf_ids = {id(o) for o in bundle.inferences}
    spec_ids = {id(o) for o in bundle.speculations}
    assert inf_ids.isdisjoint(spec_ids)


def test_signal_promotes_speculation_to_inference() -> None:
    e = event(event_type="funding", value_amount=3e8, sector="Smart Cities",
              title="Smart city mission funding released")
    t = TargetProfile(sectors=["Smart Cities"])

    without = ENGINE.detect(e, company(), t, [product("events_sponsorship")]).opportunities[0]
    assert without.epistemic_tier is EpistemicTier.speculation

    with_signal = ENGINE.detect(
        e, company(signals={"funding_signals": signal("funding_signals")}), t,
        [product("events_sponsorship")],
    ).opportunities[0]
    assert with_signal.epistemic_tier is EpistemicTier.inference     # promoted by evidence
    assert with_signal.confidence > without.confidence
    assert any(ev.kind == "company_signal" for ev in with_signal.supporting_evidence)


# --- no spurious matches -----------------------------------------------------
def test_below_threshold_or_irrelevant_produces_no_opportunity() -> None:
    e = event(event_type="tender", value_amount=1e6, sector="Agriculture", title="seed subsidy tender")
    bundle = ENGINE.detect(e, company(industry="Agriculture"), TargetProfile(),
                           [product("cybersecurity")])
    assert bundle.opportunities == []


def test_target_product_categories_restricts_output() -> None:
    e = event(sector="Defence", title="Defence data security contract")
    bundle = ENGINE.detect(
        e, company(industry="Defence"),
        TargetProfile(sectors=["Defence"], product_categories=["cybersecurity"]),
        [product("cybersecurity"), product("workforce_staffing")],
    )
    assert {o.category for o in bundle.opportunities} == {"cybersecurity"}


# --- configurable KB (not hardcoded) ----------------------------------------
def test_custom_knowledge_base_from_dict() -> None:
    kb = KnowledgeBase.from_dict({"products": [{
        "product_id": "log-1", "name": "Logistics Services", "category": "logistics",
        "trigger_event_types": ["contract_award"],
        "trigger_keywords": ["transport", "logistics", "supply"],
        "relevant_sectors": ["Logistics"],
        "business_needs": [{
            "key": "fleet", "label": "Fleet / transport capacity need", "tier": "inference",
            "timing": "0-6 months", "supporting_signals": ["expansion_activity"],
            "assumptions": ["assumes new movement of goods"], "alternatives": ["may use a 3PL"],
        }],
        "departments": ["Operations"], "job_titles": ["COO"], "weights": {"value": 0.2},
    }]})
    engine = OpportunityEngine(kb)
    e = event(sector="Logistics", title="supply chain logistics contract")
    bundle = engine.detect(e, company(industry="Logistics"), TargetProfile(), [product("logistics")])
    assert [o.category for o in bundle.opportunities] == ["logistics"]
    assert bundle.opportunities[0].need_key == "fleet"


# --- optional LLM reasoner ---------------------------------------------------
def test_reasoner_refines_without_replacing_facts() -> None:
    class FakeReasoner:
        def refine(self, opportunity, facts) -> ReasonerNote:
            return ReasonerNote(
                reasoning="LLM: " + opportunity.need_hypothesis,
                extra_alternatives=["may defer the decision to next fiscal year"],
                extra_assumptions=["assumes budget cycle aligns"],
                confidence_adjustment=0.5,   # deliberately large → must be clamped
            )

    e = event(sector="Defence", title="Defence data security contract")
    bundle = ENGINE.detect(e, company(industry="Defence"), TargetProfile(sectors=["Defence"]),
                           [product("cybersecurity")], reasoner=FakeReasoner())
    opp = bundle.opportunities[0]
    assert opp.reasoning.startswith("LLM:")
    assert "may defer the decision to next fiscal year" in opp.alternative_explanations
    assert "assumes budget cycle aligns" in opp.assumptions
    assert opp.confidence <= 0.95                 # clamp respected
    # facts are unchanged by the reasoner
    assert all(f.tier is EpistemicTier.fact for f in bundle.facts)
