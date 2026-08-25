"""End-to-end pipeline integration test.

government source → document → extraction → deduplication → company → opportunity
→ score → contact → sales brief → dashboard (API) → feedback.

Uses the real modules for every stage, with fakes only for the network, the LLM
and the contact/enrichment providers.
"""
from __future__ import annotations

import warnings
from datetime import date, datetime, timezone
from typing import ClassVar, Iterator

import httpx

warnings.filterwarnings("ignore")
from fastapi.testclient import TestClient  # noqa: E402

# --- pipeline modules ---
from app.api import create_app  # noqa: E402
from app.api.repository import InMemoryLeadRepository  # noqa: E402
from app.canonicalization import canonicalize_extracted  # noqa: E402
from app.config import Settings  # noqa: E402
from app.contacts import ContactDiscoveryService  # noqa: E402
from app.contacts.integration import contact_query_from_opportunity, to_contact_info  # noqa: E402
from app.contacts.sources import DirectorySource, ProviderSource  # noqa: E402
from app.db.enums import GovSourceType  # noqa: E402
from app.dedup.matcher import EventMatcher  # noqa: E402
from app.dedup.service import EventDeduplicator, InMemoryCandidateProvider, InMemoryEventStore  # noqa: E402
from app.brief import BriefInput, SalesBriefGenerator  # noqa: E402
from app.enrichment.service import CompanyEnrichmentService  # noqa: E402
from app.enrichment.sources.base import Article, FetchDoc  # noqa: E402
from app.enrichment.sources.news import NewsSource  # noqa: E402
from app.enrichment.sources.registry import RegistrySource  # noqa: E402
from app.enrichment.sources.website import WebsiteSource  # noqa: E402
from app.enrichment.types import CompanyRef, EnrichmentField  # noqa: E402
from app.extraction.llm import FakeLLMClient  # noqa: E402
from app.extraction.service import EventExtractionService  # noqa: E402
from app.feedback import FeedbackAnalytics, LeadMeta  # noqa: E402
from app.ingestion.base import SourceAdapter  # noqa: E402
from app.ingestion.http_client import HttpClient  # noqa: E402
from app.ingestion.pipeline import IngestionRunner  # noqa: E402
from app.ingestion.storage import InMemorySink  # noqa: E402
from app.ingestion.types import DiscoveredItem  # noqa: E402
from app.opportunity import OpportunityEngine  # noqa: E402
from app.opportunity.integration import company_profile_from_enrichment, target_profile_from_sectors  # noqa: E402
from app.opportunity.types import EpistemicTier, EventInput, Evidence as OppEvidence  # noqa: E402
from app.processing import DocumentProcessor  # noqa: E402
from app.processing.types import SourceFile  # noqa: E402
from app.scoring import LeadScoringEngine  # noqa: E402
from app.scoring.integration import scoring_input_from_opportunity  # noqa: E402
from app.brief.types import SECTION_ORDER  # noqa: E402
from tests.ing_util import allow_all_robots, make_client  # noqa: E402

NOW = datetime(2026, 8, 25, tzinfo=timezone.utc)
AS_OF = date(2026, 8, 25)
AWARDEE = "Acme Defence Systems Pvt Ltd"
TENDER = "MoD/DDP/2026/AW/1183"


# ---- stage 1: government source → document (ingestion) ----------------------
class AwardAdapter(SourceAdapter):
    name = "eProcure (fake)"
    source_type = GovSourceType.eprocurement
    base_url = "https://eprocure.gov.in/"
    # Same award reported by two portals → distinct docs, one underlying event.
    _award: ClassVar[dict] = {"awardee": AWARDEE, "value": 500000000, "buyer": "Ministry of Defence",
                              "tender": TENDER, "date": "2026-08-18",
                              "title": "Border surveillance systems", "sector": "Defence"}

    def discover(self, client: HttpClient) -> Iterator[DiscoveredItem]:
        yield DiscoveredItem(url="https://eprocure.gov.in/award/1183", payload={**self._award, "src": "eprocure"})
        yield DiscoveredItem(url="https://pib.gov.in/pr/1183", payload={**self._award, "src": "pib"})


def _extraction_envelope(user: str, _n: int) -> dict:
    return {"events": [{
        "event_type": "contract_award",
        "identifiers": {"tender_number": TENDER},
        "government_entity": "Ministry of Defence",
        "entities": [{"name": AWARDEE, "role": "awardee"}],
        "contract_value": 500000000, "currency": "INR", "sector": "Defence",
        "project": "Border surveillance systems", "award_date": "2026-08-18",
        "evidence": [{"field": "entities[0].name", "snippet": AWARDEE}], "confidence": 0.9,
    }]}


# ---- enrichment fakes -------------------------------------------------------
class FakeFetcher:
    def get(self, url):
        html = (f'<html><head><script type="application/ld+json">'
                f'{{"@type":"Organization","description":"{AWARDEE} designs surveillance and radar systems.",'
                f'"address":{{"addressLocality":"Pune","addressRegion":"Maharashtra"}}}}</script></head></html>')
        return FetchDoc(url=url, status=200, text=html)


class FakeRegistry:
    def lookup(self, *, cin=None, gstin=None, name=None):
        return {"industry": "Defence Manufacturing", "hq_location": "Pune, Maharashtra",
                "employee_range": "1001-5000", "source_url": "https://mca.gov.in/acme"}


class FakeNews:
    def search(self, query):
        return [Article("Acme launches AI threat-detection platform", "https://news/tech",
                        "Acme unveils an AI platform for surveillance analytics.", source_name="ET"),
                Article("Acme sets up new Pune facility", "https://news/exp",
                        "Expansion of manufacturing capacity in Pune.", source_name="BS")]


# ---- contact fakes ----------------------------------------------------------
class FakePeople:
    def __init__(self, rows):
        self._rows = rows

    def search(self, *, company, domain, titles):
        return list(self._rows)


def test_full_pipeline_source_to_feedback():
    # 1) INGEST -------------------------------------------------------------
    def handler(req):
        return allow_all_robots(req) or httpx.Response(404)
    sink = InMemorySink()
    report = IngestionRunner(make_client(handler), sink).run(AwardAdapter())
    assert report.stored == 2                     # two source documents preserved
    fetched = [rec.document for rec in sink.records.values()]
    assert all(d.source_url for d in fetched)     # provenance kept

    # 2) PROCESS + 3) EXTRACT ----------------------------------------------
    extractor = EventExtractionService(FakeLLMClient(handler=_extraction_envelope), now=lambda: NOW)
    extracted = []
    for doc in fetched:
        sf = SourceFile(content=doc.content, source_url=doc.source_url, source_name=doc.source_name,
                        source_type=doc.source_type, declared_mime=doc.metadata.content_type)
        outcome = DocumentProcessor().process(sf)
        assert outcome.is_success and outcome.normalized.text
        result = extractor.extract(outcome.normalized)
        assert result.is_success and result.events and not result.warnings  # grounded, no stripped claims
        extracted.extend(result.events)
    assert len(extracted) == 2

    # 4) DEDUP + COMPANY RESOLUTION ----------------------------------------
    event_store = InMemoryEventStore()
    from app.resolution.matcher import CompanyMatcher
    from app.resolution.service import CompanyResolver, InMemoryCompanyProvider, InMemoryCompanyStore
    company_store = InMemoryCompanyStore()
    deduper = EventDeduplicator(EventMatcher(), InMemoryCandidateProvider(event_store), event_store)
    resolver = CompanyResolver(CompanyMatcher(), InMemoryCompanyProvider(company_store), company_store)
    canon = canonicalize_extracted(extracted, deduplicator=deduper, resolver=resolver)
    assert len(event_store.canonicals) == 1                 # two sources → one canonical event
    assert len(next(iter(event_store.canonicals.values())).sources) == 2
    assert len(company_store.records) == 1                  # one resolved company
    assert [d.matched for d in canon.dedup] == [False, True]

    event = extracted[0]

    # 5) ENRICH -------------------------------------------------------------
    enrichment = CompanyEnrichmentService(
        [WebsiteSource(FakeFetcher(), now=lambda: NOW),
         RegistrySource(FakeRegistry(), now=lambda: NOW),
         NewsSource(FakeNews(), now=lambda: NOW)]
    ).enrich(CompanyRef(AWARDEE, website="https://acmedefence.example", cin="U123"))
    assert enrichment.field(EnrichmentField.industry).is_known
    assert enrichment.field(EnrichmentField.technology_activity).is_known   # corroborating signal

    # 6) OPPORTUNITY --------------------------------------------------------
    opp_event = EventInput(
        event_type=event.event_type, value_amount=event.contract_value, currency=event.currency,
        sector=event.sector, buyer=event.government_entity, awardee=AWARDEE, event_date=event.award_date,
        title=event.project, description=event.project,
        evidence=[OppEvidence(EpistemicTier.fact, f"{AWARDEE} won an MoD surveillance contract",
                              "event", fetched[0].source_url, AWARDEE, 0.9)])
    company_in = company_profile_from_enrichment(AWARDEE, enrichment)
    target = target_profile_from_sectors(["Defence"])
    from app.opportunity.types import ProductInput
    bundle = OpportunityEngine().detect(opp_event, company_in, target,
                                        [ProductInput("cyber-1", "Cybersecurity Services", "cybersecurity")])
    assert bundle.opportunities, "expected a cybersecurity opportunity"
    opp = bundle.opportunities[0]
    assert opp.category == "cybersecurity"
    # technology signal promoted the need and grounds it in a company fact
    assert any(ev.kind == "company_signal" for ev in opp.supporting_evidence)

    # 7) SCORE --------------------------------------------------------------
    si = scoring_input_from_opportunity(
        event=opp_event, company=company_in, target=target, opportunity=opp,
        num_contacts=1, best_contact_seniority="c_level",
        ideal_employee_ranges=[company_in.employee_range])
    score = LeadScoringEngine().score(si, as_of=AS_OF)
    assert score.total >= 80 and score.grade in {"A", "B"}
    assert sum(c.points for c in score.components) == score.total   # explainable

    # 8) CONTACT ------------------------------------------------------------
    query = contact_query_from_opportunity(opp, company_name=AWARDEE, domain="acmedefence.example")
    directory = DirectorySource(FakePeople([{"name": "Priya Rao", "title": "Chief Information Security Officer",
                                             "linkedin_url": "https://linkedin/priya"}]))
    provider = ProviderSource(FakePeople([{"name": "Priya Rao", "title": "CISO",
                                          "email": "priya@acmedefence.example"}]))
    best = ContactDiscoveryService([directory, provider]).discover(query).best()
    contact = to_contact_info(best)
    assert contact.verified and contact.name == "Priya Rao"

    # 9) SALES BRIEF --------------------------------------------------------
    brief = SalesBriefGenerator(now=lambda: NOW).generate(BriefInput(
        event=opp_event, company_name=AWARDEE, opportunity=opp,
        enrichment=enrichment, score=score, contact=contact))
    assert brief.status == "ok" and brief.verified_facts
    assert "Priya Rao" in brief.sections["who_to_contact"].text

    # 10) DASHBOARD (API) ---------------------------------------------------
    lead = _build_lead_payload(opp_event, company_in, opp, score, contact, brief, enrichment, fetched)
    repo = InMemoryLeadRepository()
    repo.add(lead)
    client = TestClient(create_app(Settings(api_keys={"k": "org-1:analyst"}), repository=repo))
    h = {"X-API-Key": "k"}

    board = client.get("/api/leads", headers=h)
    assert board.status_code == 200
    assert board.json()[0]["score"] == score.total
    detail = client.get("/api/leads/L1", headers=h).json()
    assert detail["contact"]["name"] == "Priya Rao"
    assert detail["contact"]["email"] is None or "@" in detail["contact"]["email"]  # PII only in detail
    assert any(e["source_url"] for e in detail["evidence"])         # evidence traceable
    assert sum(c["points"] for c in detail["score_components"]) == score.total

    # 11) FEEDBACK ----------------------------------------------------------
    fb = client.post("/api/leads/L1/feedback", headers=h, json={"event_type": "meeting_booked"})
    assert fb.status_code == 200 and fb.json()["status"] == "meeting"
    assert len(repo.feedback) == 1

    meta = {"L1": LeadMeta("L1", score.total, score.grade, opp_event.event_type,
                           opp.product_name, opp_event.sector, AWARDEE)}
    analytics = FeedbackAnalytics(repo.feedback.events(), meta, high_threshold=80).compute()
    assert analytics.precision_high.converted == 1
    assert analytics.precision_high.precision == 1.0


def _build_lead_payload(opp_event, company_in, opp, score, contact, brief, enrichment, fetched) -> dict:
    who = brief.sections["who_to_contact"].text
    return {
        "id": "L1", "organization_id": "org-1", "company": company_in.name, "status": "new",
        "config_version": score.config_version,
        "event": {"type": opp_event.event_type, "type_label": "Contract award", "title": opp_event.title,
                  "value": opp_event.value_amount, "org": opp_event.buyer, "sector": opp_event.sector,
                  "date": opp_event.event_date.isoformat(), "reference": TENDER,
                  "department": None, "location": None},
        "opportunity": opp.product_name, "opportunity_tier": opp.epistemic_tier.name,
        "score": score.total, "grade": score.grade, "confidence": round(opp.confidence, 2),
        "why_now": brief.sections["why_now"].text, "reason_to_call": brief.sections["reason_to_call"].text,
        "target_contact": contact.name if contact.verified else "target role",
        "company_profile": {"industry": company_in.industry, "hq": company_in.hq_location,
                            "size": company_in.employee_range, "description": company_in.description},
        "opportunity_detail": {"need": opp.need_hypothesis, "reasoning": opp.reasoning,
                               "assumptions": opp.assumptions, "alternatives": opp.alternative_explanations,
                               "timing": opp.timing},
        "evidence": [{"id": f.id, "tier": f.tier.name, "statement": f.statement, "snippet": f.evidence,
                      "source_url": f.source_url, "confidence": f.confidence} for f in brief.verified_facts],
        "score_components": [{"key": c.key, "points": c.points, "max_points": c.max_points,
                              "note": c.explanation} for c in score.components],
        "contact": {"name": contact.name, "title": contact.title, "verified": contact.verified,
                    "email": contact.email, "linkedin": contact.linkedin_url,
                    "source": None, "confidence": contact.confidence},
        "brief": [{"key": brief.sections[k].key, "title": t, "text": brief.sections[k].text,
                   "is_inference": brief.sections[k].is_inference}
                  for k, t in SECTION_ORDER if k in brief.sections],
        "risk": brief.sections["risk"].text,
        "sources": [{"title": d.source_url, "url": d.source_url, "kind": "eprocure",
                     "date": "2026-08-18"} for d in fetched],
    }
