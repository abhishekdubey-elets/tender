"""Seed a few complete demo leads into the govintel database so the running
application has real data end-to-end (government_events → companies → enrichment
→ contacts → opportunities → lead_scores → sales_briefs).

Idempotent: does nothing if the demo organization already has opportunities.

Run:  python -m scripts.seed_demo_leads
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

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
    Jurisdiction,
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
    Organization,
    Product,
    RawDocument,
    SalesBrief,
)
from app.db.session import SessionLocal
from app.scoring import LeadScoringEngine, ScoringInput

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TODAY = date(2026, 8, 26)
NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)

# (product category, human name) -> fixed product id
PRODUCTS = {
    "cybersecurity": ("Cybersecurity Services", uuid.UUID("22222222-0000-0000-0000-000000000001")),
    "cloud_infrastructure": ("Cloud & Infrastructure", uuid.UUID("22222222-0000-0000-0000-000000000002")),
}

LEADS = [
    dict(
        ref="MoD/DDP/2026/AW/1183", source="pib", src_url="https://pib.gov.in/pr/1183",
        event_type=EventType.award, etype_label="Contract award",
        title="Border surveillance & sensor systems", value=500_000_000, buyer="Ministry of Defence",
        department="Dept. of Defence Production", sector="Defence", event_date=date(2026, 8, 18),
        location="New Delhi", snippet="MoD awards Rs 50 crore surveillance contract to Acme Defence Systems.",
        company="Acme Defence Systems Pvt Ltd", cin="U74999DL2019PTC001183", industry="Defence & IT",
        hq_city="Pune", hq_state="Maharashtra", size="1001-5000", website="https://acmedefence.example",
        revenue=12_000_000_000, employees=2200, description="Designs surveillance, radar and electro-optic systems.",
        product="cybersecurity", opp_type=OpportunityType.other,
        need="Cybersecurity & data-protection need", tier="inference",
        reasoning="Acme won a Rs 50 crore border-surveillance contract handling classified sensor data; under the "
                  "Cybersecurity Services rule this suggests a data-protection and compliance need.",
        opp_conf=0.82, target_sectors=["Defence"], evidence_conf=[0.9, 0.9],
        contact=("Priya Rao", "Chief Information Security Officer", Seniority.c_level,
                 "priya.rao@acmedefence.example", "https://linkedin.example/in/priyarao"),
        timing="0-6 months",
    ),
    dict(
        ref="PSCDCL/ICCC/2026/WO/44", source="eprocure", src_url="https://eprocure.gov.in/award/psc44",
        event_type=EventType.work_order, etype_label="Work order",
        title="Integrated Command & Control Centre (ICCC)", value=1_200_000_000,
        buyer="Pune Smart City Development Corp.", department="Smart Cities Mission", sector="Smart Cities",
        event_date=date(2026, 8, 5), location="Pune, Maharashtra",
        snippet="PSCDCL issues Rs 120 crore ICCC work order to Metro Infratech.",
        company="Metro Infratech Pvt Ltd", cin="U72200KA2018PTC004400", industry="IT & Urban Infrastructure",
        hq_city="Bengaluru", hq_state="Karnataka", size="501-1000", website="https://metroinfratech.example",
        revenue=6_400_000_000, employees=800, description="Systems integrator for smart-city command centres and IoT.",
        product="cloud_infrastructure", opp_type=OpportunityType.other,
        need="Cloud/compute/networking scale-up", tier="inference",
        reasoning="Metro Infratech won a Rs 120 crore ICCC work order requiring large-scale data ingestion and "
                  "video analytics; under the Cloud & Infrastructure rule this implies a cloud/compute scale-up.",
        opp_conf=0.78, target_sectors=["Smart Cities"], evidence_conf=[0.9],
        contact=("Arjun Mehta", "Chief Technology Officer", Seniority.c_level,
                 "arjun.mehta@metroinfratech.example", "https://linkedin.example/in/arjunmehta"),
        timing="0-9 months",
    ),
    dict(
        ref="NHA/ABDM/2026/GR/210", source="pib", src_url="https://pib.gov.in/nha210",
        event_type=EventType.funding, etype_label="Funding release",
        title="ABDM digital health infrastructure grant", value=350_000_000,
        buyer="Ministry of Health & Family Welfare", department="National Health Authority", sector="Healthcare",
        event_date=date(2026, 7, 22), location="New Delhi",
        snippet="NHA releases Rs 35 crore under ABDM to Bharat Health Systems.",
        company="Bharat Health Systems Ltd", cin="U72300TG2017PLC210000", industry="Health IT",
        hq_city="Hyderabad", hq_state="Telangana", size="201-500", website="https://bharathealth.example",
        revenue=1_800_000_000, employees=380, description="Digital health records and hospital information systems.",
        product="cloud_infrastructure", opp_type=OpportunityType.other,
        need="Cloud scale-up with patient-data protection", tier="inference",
        reasoning="Bharat Health received a Rs 35 crore ABDM grant to build health-record infrastructure, implying "
                  "a cloud scale-up and, given patient data, a parallel security need.",
        opp_conf=0.72, target_sectors=["Healthcare"], evidence_conf=[0.85],
        contact=None, timing="0-9 months",
    ),
]


def _brief_md(spec, total, grade, evidence_lines) -> str:
    inf = " _(inferred)_"
    company = spec["company"]
    value_cr = f"Rs {spec['value']/1e7:.0f} crore"
    date_s = spec["event_date"].isoformat()
    if spec["contact"]:
        who = f"{spec['contact'][0]} - {spec['contact'][1]} (verified)."
        action = f"Call {spec['contact'][1]} within {spec['timing']}, leading with the award as the trigger."
    else:
        who = "No specific contact verified yet. Target roles: CTO, Head of Engineering, DPO."
        action = "Prioritise: identify the CTO and reach out within " + spec["timing"] + "."
    return "\n\n".join([
        f"## Trigger\n{company} is linked to a {spec['etype_label'].lower()} worth {value_cr} in "
        f"{spec['sector']} ({date_s}).",
        f"## Why this company\n{company}: industry {spec['industry']}; HQ {spec['hq_city']}, "
        f"{spec['hq_state']}; size {spec['size']}.",
        f"## Why now{inf}\nTimely because the event is dated {date_s} and the mandate is time-bound.",
        f"## Business need hypothesis{inf}\nHypothesis ({spec['tier']}): {spec['need']}. {spec['reasoning']}",
        f"## Who to contact\n{who}",
        f"## Reason to call{inf}\n{company}'s {spec['etype_label'].lower()} could create a "
        f"{spec['need'].lower()} - a timely fit for {PRODUCTS[spec['product']][0]}.",
        "## Evidence\n" + "\n".join(evidence_lines),
        f"## Confidence\nLead score {total}/100 (grade {grade}); opportunity confidence "
        f"{int(spec['opp_conf']*100)}%.",
        f"## Recommended next action{inf}\n{action}",
        "## Risk / uncertainty\nThis lead may be incorrect if:\n"
        "- The core need is an inference, not a verified fact\n"
        + ("- No verified decision-maker contact identified\n" if not spec["contact"] else "")
        + "- The company may address the need in-house",
    ])


def make_lead(session, spec) -> None:
    src = session.scalar(select(GovernmentSource).where(GovernmentSource.slug == spec["source"]))
    if src is None:
        src = GovernmentSource(
            name={"pib": "Press Information Bureau", "eprocure": "CPPP eProcurement"}[spec["source"]],
            slug=spec["source"], source_type=GovSourceType.pib if spec["source"] == "pib" else GovSourceType.eprocurement,
            base_url="https://pib.gov.in/" if spec["source"] == "pib" else "https://eprocure.gov.in/",
            access_method=AccessMethod.rss if spec["source"] == "pib" else AccessMethod.html)
        session.add(src)
        session.flush()

    raw = RawDocument(government_source_id=src.id, source_url=spec["src_url"],
                      content_hash=hashlib.sha256(spec["src_url"].encode()).hexdigest(), fetched_at=NOW,
                      title=spec["title"], raw_content=spec["snippet"], parsed_text=spec["snippet"])
    session.add(raw)

    company = Company(canonical_name=spec["company"], normalized_name=spec["company"].lower(),
                      cin=spec["cin"], sector=spec["industry"], hq_city=spec["hq_city"], hq_state=spec["hq_state"],
                      size_band=spec["size"], website=spec["website"], is_verified=True)
    session.add(company)
    session.flush()

    session.add(CompanyEnrichment(company_id=company.id, provider=EnrichmentProvider.registry,
                                  industry=spec["industry"], employee_count=spec["employees"],
                                  annual_revenue=spec["revenue"], confidence=0.9, fetched_at=NOW, is_current=True,
                                  data={"claims": [{"field": "business_description", "value": spec["description"],
                                                    "source_url": spec["website"]}]}))

    contact_id = None
    if spec["contact"]:
        name, title, sen, email, li = spec["contact"]
        c = Contact(company_id=company.id, full_name=name, title=title, seniority=sen, email=email,
                    linkedin_url=li, source=ContactSource.linkedin, source_url=li, confidence=0.85,
                    is_verified=True, lawful_basis="legitimate interest: business-context professional outreach (DPDP)")
        session.add(c)
        session.flush()
        contact_id = c.id

    ge = GovernmentEvent(event_type=spec["event_type"], title=spec["title"], summary=spec["snippet"],
                         buyer_name=spec["buyer"], buyer_department=spec["department"], awardee_name=spec["company"],
                         company_id=company.id, company_resolution_confidence=0.85, value_amount=spec["value"],
                         currency="INR", reference_number=spec["ref"], jurisdiction=Jurisdiction.national,
                         state=spec["hq_state"], event_date=spec["event_date"], confidence=0.88,
                         dedup_key=hashlib.sha1(spec["ref"].encode()).hexdigest(),
                         attributes={"extraction_event_type": spec["event_type"].value, "sector": spec["sector"],
                                     "location": spec["location"], "identifiers": {"tender_number": spec["ref"]}})
    session.add(ge)
    session.flush()

    es = EventSource(government_event_id=ge.id, raw_document_id=raw.id, government_source_id=src.id,
                     source_url=spec["src_url"], snippet=spec["snippet"], confidence=0.9,
                     extraction_model="claude-opus-5", is_primary=True,
                     extracted_payload={"awardee": spec["company"], "value": spec["value"]})
    session.add(es)
    session.flush()

    prod_name, prod_id = PRODUCTS[spec["product"]]
    opp = Opportunity(organization_id=ORG_ID, government_event_id=ge.id, company_id=company.id, product_id=prod_id,
                      opportunity_type=spec["opp_type"], title=spec["need"], rationale=spec["reasoning"],
                      status=OpportunityStatus.new, detected_by=DetectionMethod.rule, confidence=spec["opp_conf"])
    session.add(opp)
    session.flush()

    si = ScoringInput(event_type=spec["event_type"].value, event_value=spec["value"], event_date=spec["event_date"],
                      event_sector=spec["sector"], company_industry=spec["industry"], company_employee_range=spec["size"],
                      target_sectors=spec["target_sectors"], ideal_employee_ranges=[spec["size"]],
                      opportunity_confidence=spec["opp_conf"], evidence_confidences=spec["evidence_conf"],
                      num_contacts=1 if spec["contact"] else 0,
                      best_contact_seniority="c_level" if spec["contact"] else None)
    score = LeadScoringEngine().score(si, as_of=TODAY)
    session.add(LeadScore(opportunity_id=opp.id, score=score.total, grade=ScoreGrade[score.grade],
                          factors=score.to_factors(), model_version=score.config_version, is_current=True,
                          scored_at=NOW))

    ev_lines = [f"[S1] {spec['snippet']} - {spec['src_url']}"]
    session.add(SalesBrief(opportunity_id=opp.id, contact_id=contact_id,
                           content=_brief_md(spec, score.total, score.grade, ev_lines),
                           format=BriefFormat.markdown, status=BriefStatus.final, model="claude-opus-5",
                           prompt_version="sales-brief-v1", generated_at=NOW))
    session.add(OpportunityEvidence(opportunity_id=opp.id, evidence_type=EvidenceType.event_source,
                                    raw_document_id=raw.id, source_url=spec["src_url"],
                                    description=spec["snippet"], weight=0.9))


def main() -> None:
    with SessionLocal() as session:
        org = session.get(Organization, ORG_ID)
        if org is None:
            session.add(Organization(id=ORG_ID, name="Elets Technomedia", slug="elets", domain="elets.in"))
            session.flush()
        for cat, (name, pid) in PRODUCTS.items():
            if session.get(Product, pid) is None:
                session.add(Product(id=pid, organization_id=ORG_ID, name=name, attributes={"category": cat}))
        session.flush()

        if session.scalar(select(Opportunity).where(Opportunity.organization_id == ORG_ID)) is not None:
            print("Demo leads already present — nothing to do.")
            return
        for spec in LEADS:
            make_lead(session, spec)
        session.commit()
        n = session.scalar(select(Opportunity).where(Opportunity.organization_id == ORG_ID).with_only_columns(
            Opportunity.id))
    print(f"Seeded {len(LEADS)} demo leads for org {ORG_ID}.")


if __name__ == "__main__":
    main()
