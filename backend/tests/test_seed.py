"""The seed routine populates reference data and is idempotent."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import GovernmentSource, Organization, Product, TargetSector, User
from app.db.seed import seed


def test_seed_populates_reference_data(session: Session) -> None:
    seed(session)

    assert session.scalar(select(func.count()).select_from(GovernmentSource)) >= 4
    org = session.scalar(select(Organization).where(Organization.slug == "elets"))
    assert org is not None
    admin = session.scalar(select(User).where(User.email == "dme@elets.in"))
    assert admin is not None and admin.organization_id == org.id
    assert session.scalar(select(func.count()).select_from(TargetSector)) >= 6

    # A product is linked to at least one sector (m2m populated).
    product = session.scalar(select(Product).where(Product.name.like("Smart City%")))
    assert product is not None
    assert len(product.target_sectors) >= 1


def test_seed_is_idempotent(session: Session) -> None:
    seed(session)
    sources_after_first = session.scalar(select(func.count()).select_from(GovernmentSource))
    seed(session)
    sources_after_second = session.scalar(select(func.count()).select_from(GovernmentSource))
    assert sources_after_first == sources_after_second
