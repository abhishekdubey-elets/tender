"""Source-authority weighting: an award document must outrank a news mention."""
from __future__ import annotations

from datetime import date

from app.opportunity.types import (
    CompanyProfileInput,
    EpistemicTier,
    Evidence,
    EventInput,
    Opportunity,
    TargetProfile,
)
from app.scoring import LeadScoringEngine
from app.scoring.integration import scoring_input_from_opportunity
from app.scoring.source_authority import authority_for_url


def test_authority_for_url_ordering():
    a_award = authority_for_url("https://eprocure.gov.in/award/123")
    a_pib = authority_for_url("https://pib.gov.in/pr/1")
    a_data = authority_for_url("https://api.data.gov.in/resource/x")
    a_gov = authority_for_url("https://mohfw.gov.in/notice")
    a_news = authority_for_url("https://www.livemint.com/story")
    a_other = authority_for_url("https://random-blog.example/post")
    a_none = authority_for_url(None)

    assert a_award == 1.0
    assert a_none == 1.0                      # internal/rule evidence not penalised
    assert a_award >= a_pib >= a_data
    assert a_gov > a_news > a_other           # government beats press beats unknown
    assert 0.0 < a_other < a_gov


def _opportunity(evidence: list[Evidence]) -> Opportunity:
    return Opportunity(
        product_id="p1", product_name="Elets eGov Summit", category="sponsorship",
        need_key="sponsor", need_hypothesis="sponsor the summit", trigger="award",
        reasoning="won government money", epistemic_tier=EpistemicTier.inference,
        confidence=0.8, timing="0-3 months", supporting_evidence=evidence,
    )


def _score(opp: Opportunity):
    event = EventInput(event_type="award", value_amount=800_000_000, currency="INR",
                       sector="e-Governance", buyer="MeitY", awardee="GovStack",
                       event_date=date(2026, 8, 19), title="platform", description=None)
    company = CompanyProfileInput(name="GovStack", industry="e-Governance IT", employee_range="501-1000")
    target = TargetProfile(sectors=["e-Governance"])
    si = scoring_input_from_opportunity(
        event=event, company=company, target=target, opportunity=opp,
        num_contacts=1, best_contact_seniority="c_level",
        ideal_employee_ranges=["501-1000"], authority_of=authority_for_url,
    )
    return LeadScoringEngine().score(si, as_of=date(2026, 8, 26)), si


def test_award_evidence_outranks_news_in_scoring():
    conf = 0.9
    award = _opportunity([Evidence(EpistemicTier.fact, "award doc", "event",
                                   source_url="https://eprocure.gov.in/award/1", confidence=conf)])
    news = _opportunity([Evidence(EpistemicTier.fact, "news mention", "event",
                                  source_url="https://random-news.example/x", confidence=conf)])

    award_score, award_si = _score(award)
    news_score, news_si = _score(news)

    # the award evidence keeps full confidence; the news evidence is discounted
    assert award_si.evidence_confidences[0] == conf
    assert news_si.evidence_confidences[0] < conf
    # and that flows through to a higher (or equal) total for the award-backed lead
    assert award_score.total >= news_score.total
