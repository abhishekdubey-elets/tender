"""Repeatable Google-News → government-money leads runner.

Two subcommands bracket a multi-agent extraction step (the extraction itself runs
as a Claude workflow — see scripts/gnews_leads_workflow.md — because it needs a
model; with an ANTHROPIC_API_KEY the same could run headless):

  1. fetch   — pull Google News RSS per vertical, dedupe, write a candidates JSON.
               (deterministic, standalone, repeatable)
                     │
                     ▼   [multi-agent extract → verify → synthesize → leads JSON]
                     │
  2. persist — read the leads JSON and write them to Postgres as news-sourced,
               authority-discounted sponsorship opportunities that show on the
               dashboard (and fire the WebSocket push).

Run:
  python -m scripts.news_leads fetch --out leads_candidates.json
  python -m scripts.news_leads persist --leads leads_final.json
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.db.enums import (
    BriefFormat,
    BriefStatus,
    DetectionMethod,
    EventType,
    EvidenceType,
    GovSourceType,
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

# Reuse the demo org + per-vertical Elets summit products from the seed.
from scripts.seed_demo_leads import ICP_SECTORS, ORG_ID, PRODUCTS

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Google News is a discovery feed of news: authority 0.65 (cross-check required).
NEWS_AUTHORITY = authority_for_url("https://news.google.com/x")  # 0.65

# Per-vertical search queries. Digital Learning / eHealth get award-specific terms
# so they surface "company won government money", not ministry launches or opinion.
QUERIES: dict[str, list[str]] = {
    "e-Governance": [
        "company wins e-governance project crore government India",
        "government e-governance contract awarded company India",
    ],
    "Digital Learning": [
        "edtech company wins government school contract crore India",
        "Samagra Shiksha digital classroom contract awarded company India",
        "company wins state education department digital contract crore India",
    ],
    "Pharma": [
        "pharma company PLI incentive disbursement India",
        "pharmaceutical company government contract crore India",
    ],
    "eHealth": [
        "health IT company wins government hospital contract crore India",
        "ABDM integrator contract awarded company India",
        "hospital information system HMIS contract awarded company India",
    ],
    "Banking": [
        "company wins PSU bank IT contract crore India",
        "public sector bank awards contract to company crore India",
    ],
    "Finance": [
        "company wins government finance IT contract crore India",
        "income tax GST platform contract awarded company India",
    ],
}

VERTICAL_PRODUCT = {
    "e-Governance": "egov", "Digital Learning": "digital_learning", "Pharma": "pharma",
    "eHealth": "ehealth", "Banking": "bfsi", "Finance": "bfsi",
}


# --------------------------------------------------------------------------- #
# fetch
# --------------------------------------------------------------------------- #
def _clean(s: str | None) -> str:
    return re.sub("<[^>]+>", "", s or "").strip()


def fetch(args: argparse.Namespace) -> int:
    out: dict[str, list[dict]] = {}
    seen: set[str] = set()
    client = HttpClient(user_agent=BROWSER_UA, respect_robots=False, timeout=30.0)
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
                        items.append({
                            "title": title,
                            "source": source,
                            "date": (p.get("published") or "")[:16],
                        })
                except Exception as exc:  # noqa: BLE001
                    print(f"  ! {vertical}: {type(exc).__name__}: {exc}", file=sys.stderr)
            out[vertical] = items[: args.per_vertical]
            print(f"{vertical}: {len(out[vertical])} items")
    finally:
        client.close()
    payload = {"bySector": out}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    total = sum(len(v) for v in out.values())
    print(f"\nWrote {total} candidates to {args.out}")
    print("Next: run the multi-agent extraction workflow on this file, then "
          "`python -m scripts.news_leads persist --leads <leads.json>`.")
    return 0


# --------------------------------------------------------------------------- #
# persist
# --------------------------------------------------------------------------- #
def _amount_to_inr(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:crore|cr)\b", text, re.I)
    if m:
        return float(m.group(1).replace(",", "")) * 1e7
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*billion", text, re.I)
    if m:
        return float(m.group(1).replace(",", "")) * 1e9
    return None


def _to_date(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return datetime.strptime(text.strip()[:16], "%a, %d %b %Y").date()
    except ValueError:
        return None


def _ensure_products(session) -> None:
    org = session.get(Organization, ORG_ID)
    if org is None:
        session.add(Organization(id=ORG_ID, name="Elets Technomedia", slug="elets", domain="elets.in"))
        session.flush()
    for cat, (name, pid) in PRODUCTS.items():
        if session.get(Product, pid) is None:
            session.add(Product(id=pid, organization_id=ORG_ID, name=name, attributes={"category": cat}))
    session.flush()


def _persist_lead(session, lead: dict, now: datetime, today: date) -> str | None:
    # Agents may HTML-escape names ("Systems &amp; Solutions").
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

    prod_cat = VERTICAL_PRODUCT[vertical]
    _name, prod_id = PRODUCTS[prod_cat]

    # Idempotency: one news opportunity per (company, product).
    existing = session.scalar(
        select(Opportunity).where(
            Opportunity.organization_id == ORG_ID,
            Opportunity.company_id == company.id,
            Opportunity.product_id == prod_id,
        )
    )
    if existing is not None:
        return None

    amount = _amount_to_inr(lead.get("amount"))
    ev_date = _to_date(lead.get("date")) or today
    what = lead.get("what_won") or "government award"
    buyer = lead.get("government_buyer") or "Government of India"
    is_pli = bool(re.search(r"\bPLI\b|incentive", what, re.I))
    etype = EventType.grant if is_pli else EventType.award
    conf = float(lead.get("confidence") or 0.5)
    source = lead.get("source") or "Google News"

    ge = GovernmentEvent(
        event_type=etype, title=what[:300], summary=what, buyer_name=buyer,
        awardee_name=company_name, company_id=company.id, company_resolution_confidence=conf,
        value_amount=amount, currency="INR", jurisdiction=Jurisdiction.national,
        event_date=ev_date, confidence=conf,
        attributes={"sector": vertical, "source_kind": "news", "news_source": source,
                    "source_authority": NEWS_AUTHORITY},
    )
    session.add(ge)
    session.flush()

    opp = Opportunity(
        organization_id=ORG_ID, government_event_id=ge.id, company_id=company.id, product_id=prod_id,
        opportunity_type=OpportunityType.sponsorship,
        title=f"Sponsor Elets {vertical} Summit", rationale=lead.get("reason_to_call") or "",
        status=OpportunityStatus.new, detected_by=DetectionMethod.llm, confidence=conf,
    )
    session.add(opp)
    session.flush()

    # Score with the news source discounting the evidence confidence (authority 0.65).
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

    amount_str = lead.get("amount") or "an undisclosed amount"
    brief = "\n\n".join([
        f"## Trigger\n{company_name} reportedly won {amount_str} from {buyer} ({what}).",
        f"## Reason to call\n{lead.get('reason_to_call') or ''}",
        f"## Source\nNews: {source} ({ev_date.isoformat()}). "
        f"**News-sourced (authority {NEWS_AUTHORITY:.2f}) — cross-check against the official "
        f"award document / tender notice before outreach.**",
        f"## Confidence\nLead score {score.total}/100 (grade {score.grade}); news confidence "
        f"{int(conf*100)}%.",
    ])
    session.add(SalesBrief(opportunity_id=opp.id, content=brief, format=BriefFormat.markdown,
                           status=BriefStatus.draft, model="claude-workflow", prompt_version="gnews-v1",
                           generated_at=now))
    session.add(OpportunityEvidence(opportunity_id=opp.id, evidence_type=EvidenceType.external,
                                    source_url=None, description=f"News: {source} — {what}",
                                    weight=NEWS_AUTHORITY))
    return company_name


def persist(args: argparse.Namespace) -> int:
    with open(args.leads, encoding="utf-8") as fh:
        data = json.load(fh)
    leads = data.get("leads", data) if isinstance(data, dict) else data
    now = datetime.now(timezone.utc)
    today = now.date()
    written = []
    with SessionLocal() as session:
        _ensure_products(session)
        for lead in leads:
            name = _persist_lead(session, lead, now, today)
            if name:
                written.append(name)
        session.commit()
    print(f"Persisted {len(written)} news leads: {', '.join(written) or '(none — all duplicates)'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(description="Google-News government-money leads runner.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("fetch", help="fetch Google News per vertical -> candidates JSON")
    pf.add_argument("--out", default="leads_candidates.json", help="output candidates JSON path")
    pf.add_argument("--per-vertical", type=int, default=12, help="max items kept per vertical")
    pf.set_defaults(func=fetch)

    pp = sub.add_parser("persist", help="persist a leads JSON to Postgres as news-sourced leads")
    pp.add_argument("--leads", required=True, help="leads JSON (workflow output: {leads:[...]})")
    pp.set_defaults(func=persist)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
