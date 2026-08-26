"""SqlAlchemyLeadRepository mapping tests (transient ORM graph, no live DB)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from app.api.db_repository import SqlAlchemyLeadRepository, _parse_brief, build_detail, build_summary
from app.api.schemas import LeadDetail
from app.db.enums import (
    AccessMethod,
    BriefFormat,
    BriefStatus,
    ContactSource,
    DetectionMethod,
    EnrichmentProvider,
    EventType,
    EvidenceType,
    GovSourceType,
    OpportunityStatus,
    OpportunityType,
    ScoreGrade,
    Seniority,
)
from app.db.models import (
    Company,
    CompanyEnrichment,
    Contact,
    EventSource,
    GovernmentEvent,
    GovernmentSource,
    LeadScore,
    Opportunity,
    OpportunityEvidence,
    Product,
    RawDocument,
    SalesBrief,
)
from app.feedback.types import FeedbackEventType
from app.opportunity.knowledge_base import default_knowledge_base

NOW = datetime(2026, 8, 25, tzinfo=timezone.utc)
KB = default_knowledge_base()


def _opp():
    org = uuid.uuid4()
    gs = GovernmentSource(name="PIB", slug="pib", source_type=GovSourceType.pib,
                          base_url="https://pib.gov.in/", access_method=AccessMethod.rss)
    rd = RawDocument(government_source_id=uuid.uuid4(), source_url="https://pib.gov.in/x",
                     content_hash="h", fetched_at=NOW, title="PIB release")
    es = EventSource(source_url="https://pib.gov.in/x", snippet="MoD awards surveillance contract",
                     confidence=Decimal("0.9"))
    es.raw_document = rd
    es.government_source = gs
    ge = GovernmentEvent(event_type=EventType.award, title="Border surveillance",
                         buyer_name="Ministry of Defence", buyer_department="DDP",
                         value_amount=Decimal("500000000"), currency="INR", event_date=date(2026, 8, 18),
                         reference_number="MoD/DDP/2026/AW/1183",
                         attributes={"extraction_event_type": "contract_award", "sector": "Defence",
                                     "location": "New Delhi"})
    ge.sources = [es]
    company = Company(canonical_name="Acme Defence Systems Pvt Ltd", normalized_name="acme defence systems",
                      sector="Defence", hq_city="Pune", hq_state="Maharashtra", size_band="1001-5000",
                      website="https://acme.example")
    company.contacts = [Contact(company_id=uuid.uuid4(), full_name="Priya Rao", title="CISO",
                                seniority=Seniority.c_level, email="priya@acme.example",
                                linkedin_url="https://linkedin/priya", source=ContactSource.linkedin,
                                confidence=Decimal("0.85"), is_verified=True, do_not_contact=False)]
    company.enrichments = [CompanyEnrichment(company_id=uuid.uuid4(), provider=EnrichmentProvider.registry,
                                             industry="Defence & IT", employee_count=Decimal("2000"),
                                             annual_revenue=Decimal("1200000000"), confidence=Decimal("0.9"),
                                             fetched_at=NOW, is_current=True,
                                             data={"claims": [{"field": "business_description",
                                                               "value": "Designs surveillance systems."}]})]
    product = Product(organization_id=org, name="Cybersecurity Services",
                      attributes={"category": "cybersecurity"})
    opp = Opportunity(organization_id=org, government_event_id=uuid.uuid4(), company_id=uuid.uuid4(),
                      opportunity_type=OpportunityType.other, title="Cybersecurity & data-protection need",
                      rationale="Sensitive defence data suggests a security need.",
                      status=OpportunityStatus.new, detected_by=DetectionMethod.rule, confidence=Decimal("0.82"))
    opp.id = uuid.uuid4()
    opp.event = ge
    opp.company = company
    opp.product = product
    opp.lead_scores = [LeadScore(opportunity_id=opp.id, score=Decimal("92"), grade=ScoreGrade.A,
                                 model_version="lead-score-v1", is_current=True, scored_at=NOW,
                                 factors={"total": 92, "grade": "A", "config_version": "lead-score-v1",
                                          "components": [{"key": "sector_relevance", "label": "Sector relevance",
                                                          "points": 25, "max_points": 25, "explanation": "match"}]})]
    opp.briefs = [SalesBrief(opportunity_id=opp.id, content=(
        "## Trigger\nAcme won a contract worth 50 cr.\n\n"
        "## Why now _(inferred)_\nEvent is recent.\n\n"
        "## Risk / uncertainty\nThe core need is an inference."),
        format=BriefFormat.markdown, status=BriefStatus.final, model="claude-opus-5",
        prompt_version="sales-brief-v1", generated_at=NOW)]
    opp.evidence = [OpportunityEvidence(opportunity_id=opp.id, evidence_type=EvidenceType.event_source,
                                        source_url="https://pib.gov.in/x", description="Acme won the award",
                                        weight=Decimal("0.9"))]
    return org, opp


def test_build_summary_maps_core_fields() -> None:
    _org, opp = _opp()
    s = build_summary(opp, KB)
    assert s["company"] == "Acme Defence Systems Pvt Ltd"
    assert s["score"] == 92 and s["grade"] == "A"
    assert s["event"]["type"] == "contract_award" and s["event"]["type_label"] == "Contract award"
    assert s["event"]["value"] == 500000000.0 and s["event"]["sector"] == "Defence"
    assert s["opportunity"] == "Cybersecurity Services"
    assert s["opportunity_tier"] == "inference"          # from KB cyber need
    assert s["target_contact"] == "Priya Rao"            # verified contact


def test_build_detail_is_schema_valid_and_grounded() -> None:
    _org, opp = _opp()
    d = build_detail(opp, KB)
    LeadDetail(**d)                                       # conforms to the API contract

    assert d["company_profile"]["hq"] == "Pune, Maharashtra"
    assert d["company_profile"]["description"] == "Designs surveillance systems."
    # score components come straight from lead_scores.factors
    assert d["score_components"] == [{"key": "sector_relevance", "points": 25, "max_points": 25, "note": "match"}]
    # evidence traces to a source URL
    assert any(e["source_url"] == "https://pib.gov.in/x" for e in d["evidence"])
    # brief parsed back into structured sections
    keys = {s["key"]: s for s in d["brief"]}
    assert keys["trigger"]["is_inference"] is False
    assert keys["why_now"]["is_inference"] is True
    assert "inference" in d["risk"]
    # opportunity detail reconstructed from KB
    assert "CISO" in d["opportunity_detail"]["job_titles"]
    assert d["opportunity_detail"]["assumptions"]
    assert d["contact"]["email"] == "priya@acme.example" and d["contact"]["verified"] is True
    assert d["sources"][0]["url"] == "https://pib.gov.in/x"


def test_parse_brief_handles_flags_and_inference_tags() -> None:
    content = ("## Trigger\nX.\n\n## Reason to call _(inferred)_\nY.\n\n"
               "## Risk / uncertainty\nZ.\n\n## Flags\n- something")
    sections, risk = _parse_brief(content)
    titles = [s["title"] for s in sections]
    assert titles == ["Trigger", "Reason to call"]       # Flags & Risk excluded from sections
    assert sections[1]["is_inference"] is True and risk == "Z."


# --- repository methods over a fake session ---------------------------------
class _FakeResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None


class _FakeSession:
    def __init__(self, opps):
        self.opps = opps
        self.added = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def scalars(self, _stmt):
        return _FakeResult(self.opps)

    def get(self, _model, ident):
        return next((o for o in self.opps if o.id == ident), None)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        pass


def test_repository_list_get_and_feedback() -> None:
    org, opp = _opp()
    fake = _FakeSession([opp])
    repo = SqlAlchemyLeadRepository(lambda: fake, knowledge_base=KB)

    leads = repo.list_leads(str(org), {})
    assert len(leads) == 1 and leads[0]["score"] == 92
    assert repo.list_leads(str(org), {"score_min": 95}) == []

    assert repo.get_lead(str(org), str(opp.id))["company"] == "Acme Defence Systems Pvt Ltd"
    assert repo.get_lead(str(uuid.uuid4()), str(opp.id)) is None      # cross-tenant
    assert repo.get_lead(str(org), "not-a-uuid") is None             # bad id

    res = repo.record_feedback(str(org), str(opp.id), FeedbackEventType.meeting_booked, None, "keyid")
    assert res == {"ok": True, "status": "meeting"}
    assert opp.status is OpportunityStatus.meeting
    assert len(fake.added) == 1                                       # one immutable feedback row
