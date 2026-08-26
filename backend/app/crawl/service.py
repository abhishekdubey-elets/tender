"""Crawl service internals: fetch, rule-extract, persist, run_crawl."""
from __future__ import annotations

import html
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.db.enums import (
    BriefFormat,
    BriefStatus,
    DetectionMethod,
    EventType,
    EvidenceType,
    Jurisdiction,
    OpportunityStatus,
    OpportunityType,
    ScoreGrade,
)
from app.db.models import (
    Company,
    GovernmentEvent,
    LeadScore,
    Opportunity,
    OpportunityEvidence,
    Organization,
    Product,
    SalesBrief,
)
from app.db.session import SessionLocal
from app.ingestion.adapters.google_news import GoogleNewsRSSAdapter
from app.ingestion.http_client import HttpClient
from app.scoring import LeadScoringEngine, ScoringInput
from app.scoring.source_authority import authority_for_url

# Demo org + per-vertical Elets summit products (fixed ids; match seed_demo_leads).
ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ICP_SECTORS = ["e-Governance", "Digital Learning", "Pharma", "eHealth", "Banking", "Finance"]
PRODUCTS = {
    "egov": ("Elets eGov Summit — Sponsorship", uuid.UUID("22222222-0000-0000-0000-000000000001")),
    "digital_learning": ("Elets World Education Summit — Sponsorship", uuid.UUID("22222222-0000-0000-0000-000000000002")),
    "pharma": ("Elets Pharma Innovation Summit — Sponsorship", uuid.UUID("22222222-0000-0000-0000-000000000003")),
    "ehealth": ("Elets eHealth Summit — Sponsorship", uuid.UUID("22222222-0000-0000-0000-000000000004")),
    "bfsi": ("Elets BFSI Leadership Summit — Sponsorship", uuid.UUID("22222222-0000-0000-0000-000000000005")),
}
VERTICAL_PRODUCT = {
    "e-Governance": "egov", "Digital Learning": "digital_learning", "Pharma": "pharma",
    "eHealth": "ehealth", "Banking": "bfsi", "Finance": "bfsi",
}

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
NEWS_AUTHORITY = authority_for_url("https://news.google.com/x")  # 0.65

QUERIES: dict[str, list[str]] = {
    "e-Governance": [
        "company wins e-governance project crore government India",
        "government e-governance contract awarded company India",
    ],
    "Digital Learning": [
        "edtech company wins government school contract crore India",
        "company wins state education department digital contract crore India",
    ],
    "Pharma": [
        "pharma company PLI incentive disbursement India",
    ],
    "eHealth": [
        "health IT company wins government hospital contract crore India",
        "hospital information system HMIS contract awarded company India",
    ],
    "Banking": [
        "company wins PSU bank IT contract crore India",
    ],
    "Finance": [
        "company wins government finance IT contract crore India",
        "income tax GST platform contract awarded company India",
    ],
}


@dataclass
class CrawlReport:
    started_at: str
    fetched: int = 0
    extracted: int = 0
    persisted: int = 0
    companies: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def as_dict(self) -> dict:
        return {
            "started_at": self.started_at, "fetched": self.fetched,
            "extracted": self.extracted, "persisted": self.persisted,
            "companies": self.companies, "duration_ms": round(self.duration_ms, 1),
        }


# --------------------------------------------------------------------------- #
# fetch
# --------------------------------------------------------------------------- #
def _clean(s: str | None) -> str:
    return re.sub("<[^>]+>", "", s or "").strip()


def fetch_candidates(per_vertical: int = 10, client: HttpClient | None = None) -> dict[str, list[dict]]:
    own = client is None
    client = client or HttpClient(user_agent=BROWSER_UA, respect_robots=False, timeout=30.0)
    out: dict[str, list[dict]] = {}
    seen: set[str] = set()
    try:
        for vertical, queries in QUERIES.items():
            items: list[dict] = []
            for query in queries:
                try:
                    for it in GoogleNewsRSSAdapter(query).discover(client):
                        p = it.payload or {}
                        title = _clean(p.get("title"))
                        key = re.sub(r"\W+", "", title.lower())[:60]
                        if not title or key in seen:
                            continue
                        seen.add(key)
                        source = title.rsplit(" - ", 1)[-1] if " - " in title else ""
                        items.append({"title": title, "source": source,
                                      "date": (p.get("published") or "")[:16]})
                except Exception:  # noqa: BLE001 - one bad query must not abort the crawl
                    continue
            out[vertical] = items[:per_vertical]
    finally:
        if own:
            client.close()
    return out


# --------------------------------------------------------------------------- #
# rule-based extraction (headless, no model)
# --------------------------------------------------------------------------- #
_AMOUNT_RE = re.compile(r"(?:₹|Rs\.?)\s?([\d,]+(?:\.\d+)?)\s*(crore|cr|billion)\b", re.I)
_VERB_RE = re.compile(r"\b(wins?|secures?|bags?|gets?|awarded|receives?|clinches?|signs?)\b", re.I)
_GOV_MARKERS = (
    "government", "govt", "ministry", "psu", "public sector", "state bank", "central bank",
    "bank of india", "bank of baroda", "canara", "union bank", "punjab", "railway", "railtel",
    "nhai", "cbdt", "gst", "abdm", "samagra", "mahajyoti", "corporation", "municipal",
    "authority", "board", "council", "pli", "incentive", "department", "nagar", "welfare",
    "arunachal", "odisha", "tamil nadu", "uttar pradesh", "andhra", "karnataka", "goa",
)
_NOISE_MARKERS = (
    "stocks to watch", "stock to watch", "market size", "market share", " ipo", "earnings",
    "opinion", "cagr", "drhp", "52-week", "drdo", "defence", "malawi", "nigeria", "bahrain",
    "uk-india", "pre-announcement", "backgrounder",
)
_FROM_RE = re.compile(r"\bfrom\s+([A-Z][\w&.\- ]+?)(?:\s+(?:for|to|under|worth|in)\b|[,.\-]|$)")


def _amount_to_inr(text: str | None) -> float | None:
    if not text:
        return None
    m = _AMOUNT_RE.search(text)
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    return val * (1e9 if m.group(2).lower() == "billion" else 1e7)


def _to_date(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return datetime.strptime(text.strip()[:16], "%a, %d %b %Y").date()
    except ValueError:
        return None


def extract_rule_based(by_sector: dict[str, list[dict]]) -> list[dict]:
    """Conservative extraction: keep only clear "company won <amount> from a
    government counterparty" headlines. Precision over recall."""
    leads: list[dict] = []
    for vertical, items in by_sector.items():
        for it in items:
            title = it.get("title") or ""
            low = title.lower()
            if any(n in low for n in _NOISE_MARKERS):
                continue
            amt = _AMOUNT_RE.search(title)
            verb = _VERB_RE.search(title)
            if not amt or not verb or not any(g in low for g in _GOV_MARKERS):
                continue
            company = title[: verb.start()].strip(" -–—:")
            # trim a trailing source that slipped in, and cap length
            company = re.split(r"\s[-–—]\s", company)[0].strip()
            if not company or len(company) > 80:
                continue
            buyer_m = _FROM_RE.search(title)
            buyer = buyer_m.group(1).strip() if buyer_m else "Government (India)"
            amount_str = amt.group(0)
            leads.append({
                "company": company, "vertical": vertical, "government_buyer": buyer,
                "amount": amount_str, "what_won": title, "source": it.get("source") or "Google News",
                "date": it.get("date"), "confidence": 0.5,
                "reason_to_call": (f"{company} reportedly won {amount_str} in {vertical} government "
                                   f"business — invite them to sponsor the Elets {vertical} summit "
                                   f"to reach the government buyers who attend."),
            })
    return leads


# --------------------------------------------------------------------------- #
# persist
# --------------------------------------------------------------------------- #
def _ensure_products(session) -> None:
    if session.get(Organization, ORG_ID) is None:
        session.add(Organization(id=ORG_ID, name="Elets Technomedia", slug="elets", domain="elets.in"))
        session.flush()
    for cat, (name, pid) in PRODUCTS.items():
        if session.get(Product, pid) is None:
            session.add(Product(id=pid, organization_id=ORG_ID, name=name, attributes={"category": cat}))
    session.flush()


def _persist_lead(session, lead: dict, now: datetime, today: date) -> str | None:
    lead = {k: (html.unescape(v) if isinstance(v, str) else v) for k, v in lead.items()}
    company_name = (lead.get("company") or "").strip()
    vertical = lead.get("vertical") or ""
    if not company_name or vertical not in VERTICAL_PRODUCT:
        return None
    normalized = company_name.lower()

    company = session.scalar(select(Company).where(Company.normalized_name == normalized))
    if company is None:
        company = Company(canonical_name=company_name, normalized_name=normalized,
                          sector=vertical, is_verified=False)
        session.add(company)
        session.flush()

    _name, prod_id = PRODUCTS[VERTICAL_PRODUCT[vertical]]
    if session.scalar(select(Opportunity).where(
        Opportunity.organization_id == ORG_ID, Opportunity.company_id == company.id,
        Opportunity.product_id == prod_id,
    )) is not None:
        return None  # idempotent: one news opportunity per company+product

    amount = _amount_to_inr(lead.get("amount"))
    ev_date = _to_date(lead.get("date")) or today
    what = lead.get("what_won") or "government award"
    buyer = lead.get("government_buyer") or "Government of India"
    etype = EventType.grant if re.search(r"\bPLI\b|incentive", what, re.I) else EventType.award
    conf = float(lead.get("confidence") or 0.5)
    source = lead.get("source") or "Google News"

    ge = GovernmentEvent(
        event_type=etype, title=what[:300], summary=what, buyer_name=buyer, awardee_name=company_name,
        company_id=company.id, company_resolution_confidence=conf, value_amount=amount, currency="INR",
        jurisdiction=Jurisdiction.national, event_date=ev_date, confidence=conf,
        attributes={"sector": vertical, "source_kind": "news", "news_source": source,
                    "source_authority": NEWS_AUTHORITY},
    )
    session.add(ge)
    session.flush()

    opp = Opportunity(
        organization_id=ORG_ID, government_event_id=ge.id, company_id=company.id, product_id=prod_id,
        opportunity_type=OpportunityType.sponsorship, title=f"Sponsor Elets {vertical} Summit",
        rationale=lead.get("reason_to_call") or "", status=OpportunityStatus.new,
        detected_by=DetectionMethod.llm, confidence=conf,
    )
    session.add(opp)
    session.flush()

    si = ScoringInput(
        event_type=etype.value, event_value=amount, event_date=ev_date, event_sector=vertical,
        company_industry=vertical, company_employee_range=None, target_sectors=ICP_SECTORS,
        ideal_employee_ranges=None, opportunity_confidence=conf,
        evidence_confidences=[conf * NEWS_AUTHORITY], num_contacts=0, best_contact_seniority=None,
    )
    score = LeadScoringEngine().score(si, as_of=today)
    session.add(LeadScore(opportunity_id=opp.id, score=score.total, grade=ScoreGrade[score.grade],
                          factors=score.to_factors(), model_version=score.config_version,
                          is_current=True, scored_at=now))

    brief = "\n\n".join([
        f"## Trigger\n{company_name} reportedly won {lead.get('amount') or 'an award'} from {buyer} ({what}).",
        f"## Reason to call\n{lead.get('reason_to_call') or ''}",
        f"## Source\nNews: {source} ({ev_date.isoformat()}). **News-sourced (authority "
        f"{NEWS_AUTHORITY:.2f}) — cross-check against the official award document before outreach.**",
        f"## Confidence\nLead score {score.total}/100 (grade {score.grade}); news confidence {int(conf*100)}%.",
    ])
    session.add(SalesBrief(opportunity_id=opp.id, content=brief, format=BriefFormat.markdown,
                           status=BriefStatus.draft, model="rule-extractor", prompt_version="gnews-v1",
                           generated_at=now))
    session.add(OpportunityEvidence(opportunity_id=opp.id, evidence_type=EvidenceType.external,
                                    source_url=None, description=f"News: {source} — {what}",
                                    weight=NEWS_AUTHORITY))
    return company_name


def persist_leads(leads: list[dict], session_factory=SessionLocal) -> list[str]:
    now = datetime.now(timezone.utc)
    today = now.date()
    written: list[str] = []
    with session_factory() as session:
        _ensure_products(session)
        for lead in leads:
            name = _persist_lead(session, lead, now, today)
            if name:
                written.append(name)
        session.commit()
    return written


def run_crawl(per_vertical: int = 10, session_factory=SessionLocal) -> CrawlReport:
    import time

    now = datetime.now(timezone.utc)
    report = CrawlReport(started_at=now.isoformat())
    t0 = time.perf_counter()
    by_sector = fetch_candidates(per_vertical=per_vertical)
    report.fetched = sum(len(v) for v in by_sector.values())
    leads = extract_rule_based(by_sector)
    report.extracted = len(leads)
    written = persist_leads(leads, session_factory=session_factory)
    report.persisted = len(written)
    report.companies = written
    report.duration_ms = (time.perf_counter() - t0) * 1000
    return report
