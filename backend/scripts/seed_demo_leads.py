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

# Elets' government-event verticals — the ICP. A company that just won government
# money in one of these sectors is a sponsorship prospect for the matching summit.
ICP_SECTORS = ["e-Governance", "Digital Learning", "Pharma", "eHealth", "Banking", "Finance"]

# (product category, human name) -> fixed product id. Products are Elets event
# sponsorship offerings, one per vertical.
PRODUCTS = {
    "egov": ("Elets eGov Summit — Sponsorship", uuid.UUID("22222222-0000-0000-0000-000000000001")),
    "digital_learning": ("Elets World Education Summit — Sponsorship", uuid.UUID("22222222-0000-0000-0000-000000000002")),
    "pharma": ("Elets Pharma Innovation Summit — Sponsorship", uuid.UUID("22222222-0000-0000-0000-000000000003")),
    "ehealth": ("Elets eHealth Summit — Sponsorship", uuid.UUID("22222222-0000-0000-0000-000000000004")),
    "bfsi": ("Elets BFSI Leadership Summit — Sponsorship", uuid.UUID("22222222-0000-0000-0000-000000000005")),
}

LEADS = [
    dict(
        ref="MeitY/NeGD/2026/AW/3312", source="pib", src_url="https://pib.gov.in/pr/3312",
        event_type=EventType.award, etype_label="Contract award",
        title="National citizen-services platform (DigiLocker integration)", value=800_000_000,
        buyer="Ministry of Electronics & IT", department="National e-Governance Division", sector="e-Governance",
        event_date=date(2026, 8, 19), location="New Delhi",
        snippet="MeitY awards Rs 80 crore citizen-services platform contract to GovStack Technologies.",
        company="GovStack Technologies Pvt Ltd", cin="U72200UP2016PTC331200", industry="e-Governance IT",
        hq_city="Noida", hq_state="Uttar Pradesh", size="501-1000", website="https://govstack.example",
        revenue=4_500_000_000, employees=900, description="Builds citizen-service portals and digital public infrastructure for state and central government.",
        product="egov",
        need="Sponsor Elets eGov Summit 2026", tier="inference",
        reasoning="GovStack just won a marquee Rs 80 crore central e-governance platform contract, so it has fresh "
                  "budget and a strong incentive to showcase the win to the state and central buyers who attend the "
                  "eGov Summit — a high-fit sponsorship prospect.",
        opp_conf=0.86, target_sectors=ICP_SECTORS, evidence_conf=[0.9, 0.9],
        contact=("Rahul Verma", "VP – Government Business", Seniority.vp,
                 "rahul.verma@govstack.example", "https://linkedin.example/in/rahulverma"),
        timing="0-3 months",
    ),
    dict(
        ref="MoE/SS/2026/WO/778", source="eprocure", src_url="https://eprocure.gov.in/award/ss778",
        event_type=EventType.work_order, etype_label="Work order",
        title="Smart classrooms & LMS rollout (Samagra Shiksha)", value=450_000_000,
        buyer="Dept. of School Education (Rajasthan)", department="Samagra Shiksha Abhiyan", sector="Digital Learning",
        event_date=date(2026, 8, 12), location="Jaipur, Rajasthan",
        snippet="Rajasthan awards Rs 45 crore smart-classroom and LMS contract to EduSphere Learning.",
        company="EduSphere Learning Pvt Ltd", cin="U80904RJ2015PTC047780", industry="EdTech",
        hq_city="Jaipur", hq_state="Rajasthan", size="201-500", website="https://edusphere.example",
        revenue=1_600_000_000, employees=420, description="Digital classroom, LMS and assessment platforms for government schools.",
        product="digital_learning",
        need="Sponsor Elets World Education Summit 2026", tier="inference",
        reasoning="EduSphere just won a Rs 45 crore state education rollout; with a proven government reference it is "
                  "well placed to win more states and has a clear reason to be visible to education secretaries at the "
                  "World Education Summit.",
        opp_conf=0.80, target_sectors=ICP_SECTORS, evidence_conf=[0.9],
        contact=("Sneha Kulkarni", "Chief Executive Officer", Seniority.c_level,
                 "sneha.kulkarni@edusphere.example", "https://linkedin.example/in/snehakulkarni"),
        timing="0-4 months",
    ),
    dict(
        ref="DoP/PLI/2026/GR/091", source="pib", src_url="https://pib.gov.in/pr/pli091",
        event_type=EventType.grant, etype_label="Incentive / grant",
        title="PLI incentive for domestic API manufacturing", value=1_200_000_000,
        buyer="Dept. of Pharmaceuticals", department="PLI Scheme (Bulk Drugs)", sector="Pharma",
        event_date=date(2026, 8, 3), location="New Delhi",
        snippet="Dept. of Pharmaceuticals sanctions Rs 120 crore PLI incentive to Meditrust Pharma.",
        company="Meditrust Pharma Ltd", cin="L24239MH2011PLC090910", industry="Pharmaceuticals",
        hq_city="Mumbai", hq_state="Maharashtra", size="1001-5000", website="https://meditrust.example",
        revenue=9_800_000_000, employees=2600, description="Manufactures active pharmaceutical ingredients and generic formulations.",
        product="pharma",
        need="Sponsor Elets Pharma Innovation Summit 2026", tier="inference",
        reasoning="Meditrust just secured a Rs 120 crore PLI incentive, signalling a large capacity expansion and a "
                  "public-affairs agenda; sponsoring the Pharma Innovation Summit puts it in front of the health and "
                  "pharma policymakers shaping the scheme.",
        opp_conf=0.74, target_sectors=ICP_SECTORS, evidence_conf=[0.85],
        contact=None, timing="0-6 months",
    ),
    dict(
        ref="NHA/ABDM/2026/GR/210", source="pib", src_url="https://pib.gov.in/nha210",
        event_type=EventType.funding, etype_label="Funding release",
        title="ABDM telemedicine & health-records rollout", value=350_000_000,
        buyer="Ministry of Health & Family Welfare", department="National Health Authority", sector="eHealth",
        event_date=date(2026, 7, 29), location="New Delhi",
        snippet="NHA releases Rs 35 crore under ABDM to Arogya HealthTech for telemedicine rollout.",
        company="Arogya HealthTech Pvt Ltd", cin="U72300TG2017PTC210000", industry="Health IT",
        hq_city="Hyderabad", hq_state="Telangana", size="201-500", website="https://arogyahealth.example",
        revenue=1_800_000_000, employees=380, description="Telemedicine, ABHA-linked health records and hospital information systems.",
        product="ehealth",
        need="Sponsor Elets eHealth Summit 2026", tier="inference",
        reasoning="Arogya just received a Rs 35 crore ABDM award to scale telemedicine nationally; the eHealth Summit "
                  "is where the National Health Authority and state health missions convene, making it a natural "
                  "platform for Arogya to build its next set of government relationships.",
        opp_conf=0.78, target_sectors=ICP_SECTORS, evidence_conf=[0.9],
        contact=("Dr. Kavya Nair", "Chief Technology Officer", Seniority.c_level,
                 "kavya.nair@arogyahealth.example", "https://linkedin.example/in/kavyanair"),
        timing="0-5 months",
    ),
    dict(
        ref="PNB/DBT/2026/AW/556", source="eprocure", src_url="https://eprocure.gov.in/award/pnb556",
        event_type=EventType.award, etype_label="Contract award",
        title="Core-banking & digital-banking modernization", value=900_000_000,
        buyer="Punjab & Sind Bank (PSU)", department="IT Modernization Programme", sector="Banking",
        event_date=date(2026, 8, 14), location="New Delhi",
        snippet="Punjab & Sind Bank awards Rs 90 crore core-banking modernization contract to FinServe Technologies.",
        company="FinServe Technologies Pvt Ltd", cin="U72200KA2014PTC055600", industry="Banking Technology",
        hq_city="Bengaluru", hq_state="Karnataka", size="1001-5000", website="https://finserve.example",
        revenue=7_200_000_000, employees=1900, description="Core-banking, digital-lending and payments platforms for banks and PSUs.",
        product="bfsi",
        need="Sponsor Elets BFSI Leadership Summit 2026", tier="inference",
        reasoning="FinServe just won a Rs 90 crore PSU core-banking modernization deal; the BFSI Leadership Summit is "
                  "attended by public-sector-bank CIOs, exactly the buyers FinServe wants for its next wave of "
                  "modernization mandates.",
        opp_conf=0.82, target_sectors=ICP_SECTORS, evidence_conf=[0.9, 0.85],
        contact=("Aditya Sharma", "Chief Revenue Officer", Seniority.c_level,
                 "aditya.sharma@finserve.example", "https://linkedin.example/in/adityasharma"),
        timing="0-4 months",
    ),
    dict(
        ref="MoF/DBT/2026/WO/402", source="eprocure", src_url="https://eprocure.gov.in/award/dbt402",
        event_type=EventType.work_order, etype_label="Work order",
        title="State treasury & DBT digitization platform", value=600_000_000,
        buyer="Dept. of Finance (Madhya Pradesh)", department="Direct Benefit Transfer Cell", sector="Finance",
        event_date=date(2026, 8, 9), location="Bhopal, Madhya Pradesh",
        snippet="Madhya Pradesh Finance Dept awards Rs 60 crore treasury/DBT platform contract to PayNext Solutions.",
        company="PayNext Solutions Pvt Ltd", cin="U65999MP2016PTC040200", industry="FinTech",
        hq_city="Indore", hq_state="Madhya Pradesh", size="501-1000", website="https://paynext.example",
        revenue=3_100_000_000, employees=640, description="Government payments, treasury and Direct Benefit Transfer platforms.",
        product="bfsi",
        need="Sponsor Elets BFSI Leadership Summit 2026", tier="inference",
        reasoning="PayNext just won a Rs 60 crore state treasury/DBT platform; with one state live it is chasing "
                  "others, and the BFSI/Banking & Finance Post platform reaches the finance secretaries who make "
                  "these decisions.",
        opp_conf=0.76, target_sectors=ICP_SECTORS, evidence_conf=[0.88],
        contact=("Nikhil Jain", "VP – Public Sector Sales", Seniority.vp,
                 "nikhil.jain@paynext.example", "https://linkedin.example/in/nikhiljain"),
        timing="0-6 months",
    ),
]


def _brief_md(spec, total, grade, evidence_lines) -> str:
    inf = " _(inferred)_"
    company = spec["company"]
    value_cr = f"Rs {spec['value']/1e7:.0f} crore"
    date_s = spec["event_date"].isoformat()
    event = PRODUCTS[spec["product"]][0].split(" — ")[0]
    if spec["contact"]:
        who = f"{spec['contact'][0]} - {spec['contact'][1]} (verified)."
        action = (f"Call {spec['contact'][1]} within {spec['timing']}. Open by congratulating them on the "
                  f"{value_cr} win, then invite them to sponsor {event}.")
    else:
        who = "No specific contact verified yet. Target roles: CMO / VP Marketing, Head of Government Business, CEO."
        action = f"Identify the marketing / government-business lead and pitch a {event} sponsorship within {spec['timing']}."
    return "\n\n".join([
        f"## Trigger\n{company} just won a {spec['etype_label'].lower()} worth {value_cr} in "
        f"{spec['sector']} ({date_s}) — fresh government revenue and a reason to raise its profile.",
        f"## Why this company\n{company}: industry {spec['industry']}; HQ {spec['hq_city']}, "
        f"{spec['hq_state']}; size {spec['size']}. Active in a sector Elets convenes.",
        f"## Why now{inf}\nThe win is dated {date_s}; budget and appetite for visibility are highest right after a "
        f"public award, while the story is still current.",
        f"## Sponsorship fit{inf}\n{spec['reasoning']}",
        f"## Who to contact\n{who}",
        f"## Reason to call{inf}\n{company} just won {value_cr} in {spec['sector']} government business — "
        f"congratulate them and invite them to put that win in front of the government buyers who attend {event}.",
        "## Evidence\n" + "\n".join(evidence_lines),
        f"## Confidence\nLead score {total}/100 (grade {grade}); opportunity confidence "
        f"{int(spec['opp_conf']*100)}%.",
        f"## Recommended next action{inf}\n{action}",
        "## Risk / uncertainty\nThis lead may be incorrect if:\n"
        "- The sponsorship fit is an inference, not a stated intent\n"
        + ("- No verified decision-maker contact identified\n" if not spec["contact"] else "")
        + "- The company may have no events/marketing budget this cycle",
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
                      opportunity_type=OpportunityType.sponsorship, title=spec["need"], rationale=spec["reasoning"],
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


def _reset_demo(session) -> None:
    """Delete demo content so the board can be reseeded (e.g. after changing the
    target sectors). Only touches the demo org's leads and the content tables the
    seed itself creates."""
    from sqlalchemy import delete

    from app.db.models import (
        CompanyEnrichment,
        Contact,
        EventSource,
        LeadScore,
        OpportunityEvidence,
        SalesBrief,
        SalesFeedback,
    )

    opp_ids = list(session.scalars(select(Opportunity.id).where(Opportunity.organization_id == ORG_ID)))
    if opp_ids:
        for model in (SalesFeedback, LeadScore, SalesBrief, OpportunityEvidence):
            session.execute(delete(model).where(model.opportunity_id.in_(opp_ids)))
        session.execute(delete(Opportunity).where(Opportunity.id.in_(opp_ids)))
    # Content tables are demo-only here; clear them wholesale so companies/events
    # from a previous sector configuration don't linger.
    for model in (EventSource, OpportunityEvidence, SalesBrief, LeadScore, Contact,
                  CompanyEnrichment, GovernmentEvent, RawDocument, Company):
        session.execute(delete(model))
    session.flush()


def main(reset: bool = False) -> None:
    with SessionLocal() as session:
        org = session.get(Organization, ORG_ID)
        if org is None:
            session.add(Organization(id=ORG_ID, name="Elets Technomedia", slug="elets", domain="elets.in"))
            session.flush()

        if reset:
            _reset_demo(session)

        for cat, (name, pid) in PRODUCTS.items():
            existing = session.get(Product, pid)
            if existing is None:
                session.add(Product(id=pid, organization_id=ORG_ID, name=name, attributes={"category": cat}))
            else:
                existing.name = name
                existing.attributes = {"category": cat}
        session.flush()

        if session.scalar(select(Opportunity).where(Opportunity.organization_id == ORG_ID)) is not None:
            print("Demo leads already present — nothing to do. Re-run with --reset to refresh.")
            return
        for spec in LEADS:
            make_lead(session, spec)
        session.commit()
    print(f"Seeded {len(LEADS)} demo leads for org {ORG_ID} across sectors: {', '.join(ICP_SECTORS)}.")


if __name__ == "__main__":
    import sys

    main(reset="--reset" in sys.argv)
