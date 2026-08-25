"""Seed data.

Idempotent: safe to run repeatedly. Populates the reference data that later
pipeline stages depend on — the catalogue of government sources — plus a demo
tenant (organization, admin user, target sectors and products) so the schema
can be exercised end-to-end.

Run with:  python -m app.db.seed
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import (
    AccessMethod,
    GovSourceType,
    Jurisdiction,
    UserRole,
)
from app.db.models import (
    GovernmentSource,
    Organization,
    Product,
    TargetSector,
    User,
)
from app.db.session import SessionLocal

GOVERNMENT_SOURCES = [
    {
        "slug": "gem",
        "name": "Government e-Marketplace (GeM)",
        "source_type": GovSourceType.gem,
        "base_url": "https://gem.gov.in/",
        "access_method": AccessMethod.playwright,
        "jurisdiction": Jurisdiction.national,
    },
    {
        "slug": "cppp-eprocure",
        "name": "Central Public Procurement Portal (eProcure)",
        "source_type": GovSourceType.eprocurement,
        "base_url": "https://eprocure.gov.in/",
        "access_method": AccessMethod.html,
        "jurisdiction": Jurisdiction.national,
    },
    {
        "slug": "pib",
        "name": "Press Information Bureau",
        "source_type": GovSourceType.pib,
        "base_url": "https://pib.gov.in/",
        "access_method": AccessMethod.rss,
        "jurisdiction": Jurisdiction.national,
    },
    {
        "slug": "egazette",
        "name": "The Gazette of India",
        "source_type": GovSourceType.gazette,
        "base_url": "https://egazette.gov.in/",
        "access_method": AccessMethod.html,
        "jurisdiction": Jurisdiction.national,
    },
]

DEMO_ORG = {
    "slug": "elets",
    "name": "Elets Technomedia",
    "domain": "elets.in",
    "description": "Events, media and knowledge-sharing across governance verticals.",
}

DEMO_ADMIN = {
    "email": "dme@elets.in",
    "full_name": "Platform Admin",
    "role": UserRole.admin,
}

# (sector name, description, keywords)
TARGET_SECTORS = [
    ("Smart Cities", "Smart-city and urban-tech programmes.", ["smart city", "urban", "iccc", "gis"]),
    ("BFSI", "Banking, financial services and insurance.", ["bank", "fintech", "insurance", "nbfc"]),
    ("Education & EdTech", "Higher/school education and edtech.", ["education", "edtech", "university", "skill"]),
    ("Healthcare", "Public and digital health.", ["health", "hospital", "abdm", "telemedicine"]),
    ("Urban Infrastructure", "Roads, water, transit, utilities.", ["infrastructure", "water", "metro", "road"]),
    ("e-Governance", "Digital government and citizen services.", ["e-governance", "digital india", "citizen services"]),
]

# (product name, description, sector names it maps to)
PRODUCTS = [
    ("Smart City Summit — Sponsorship", "Headline/associate sponsorship packages.", ["Smart Cities", "Urban Infrastructure"]),
    ("BFSI Leadership Summit — Sponsorship", "BFSI event sponsorship.", ["BFSI"]),
    ("EdTech Conclave — Exhibition", "Exhibition booths and speaking slots.", ["Education & EdTech"]),
    ("eGov Magazine — Advertising", "Print/digital advertising placements.", ["e-Governance", "Smart Cities"]),
]


def seed(session: Session) -> None:
    # --- Government sources ---
    for spec in GOVERNMENT_SOURCES:
        exists = session.scalar(
            select(GovernmentSource).where(GovernmentSource.slug == spec["slug"])
        )
        if not exists:
            session.add(GovernmentSource(**spec))

    # --- Demo organization ---
    org = session.scalar(select(Organization).where(Organization.slug == DEMO_ORG["slug"]))
    if not org:
        org = Organization(**DEMO_ORG)
        session.add(org)
        session.flush()  # assign org.id

    # --- Admin user ---
    admin = session.scalar(select(User).where(User.email == DEMO_ADMIN["email"]))
    if not admin:
        session.add(User(organization_id=org.id, **DEMO_ADMIN))

    # --- Target sectors ---
    sectors: dict[str, TargetSector] = {}
    for name, description, keywords in TARGET_SECTORS:
        sector = session.scalar(
            select(TargetSector).where(
                TargetSector.organization_id == org.id, TargetSector.name == name
            )
        )
        if not sector:
            sector = TargetSector(
                organization_id=org.id, name=name, description=description, keywords=keywords
            )
            session.add(sector)
            session.flush()
        sectors[name] = sector

    # --- Products (with sector links) ---
    for name, description, sector_names in PRODUCTS:
        product = session.scalar(
            select(Product).where(
                Product.organization_id == org.id, Product.name == name
            )
        )
        if not product:
            product = Product(organization_id=org.id, name=name, description=description)
            product.target_sectors = [sectors[s] for s in sector_names if s in sectors]
            session.add(product)

    session.flush()


def main() -> None:
    with SessionLocal() as session:
        seed(session)
        session.commit()
    print("Seed complete.")


if __name__ == "__main__":
    main()
