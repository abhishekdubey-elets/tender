"""Tenant-side entities: the *customer* of the platform.

An :class:`Organization` is a business that uses the platform ("my business").
Its :class:`User` accounts, :class:`TargetSector` definitions and
:class:`Product` catalogue describe the Ideal Customer Profile that
opportunity-detection later reasons against. These are configuration, not
harvested government data.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003  (runtime-needed for Mapped[] resolution)
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import UserRole

if TYPE_CHECKING:
    from app.db.models.opportunities import Opportunity


# Many-to-many: a product can address several target sectors, and a sector can
# be served by several products.
product_target_sectors = Table(
    "product_target_sectors",
    Base.metadata,
    Column(
        "product_id",
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "target_sector_id",
        ForeignKey("target_sectors.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    users: Mapped[list["User"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    target_sectors: Mapped[list["TargetSector"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    products: Mapped[list["Product"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="organization")

    __table_args__ = (UniqueConstraint("slug", name="uq_organizations_slug"),)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"), nullable=False, server_default=UserRole.viewer.value
    )
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_login_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True))

    organization: Mapped["Organization"] = relationship(back_populates="users")

    __table_args__ = (
        # Case-insensitive uniqueness of login email across the platform.
        Index("uq_users_lower_email", func.lower(email), unique=True),
        Index("ix_users_organization_id", "organization_id"),
    )


class TargetSector(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "target_sectors"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Free-form matching hints used by opportunity-detection (e.g. keywords,
    # NIC/NAICS codes). Stored as JSONB so the rule layer can evolve without
    # a migration.
    keywords: Mapped[list | None] = mapped_column(JSONB)
    nic_codes: Mapped[list | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    organization: Mapped["Organization"] = relationship(back_populates="target_sectors")
    products: Mapped[list["Product"]] = relationship(
        secondary=product_target_sectors, back_populates="target_sectors"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_target_sectors_organization_id_name"),
    )


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    organization: Mapped["Organization"] = relationship(back_populates="products")
    target_sectors: Mapped[list["TargetSector"]] = relationship(
        secondary=product_target_sectors, back_populates="products"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_products_organization_id_name"),
    )
