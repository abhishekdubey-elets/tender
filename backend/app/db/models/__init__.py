"""ORM model registry.

Importing this package imports every model module so that SQLAlchemy's mapper
configuration (and Alembic autogenerate / ``Base.metadata``) sees the full set
of tables. Import order does not matter because relationships are declared with
string targets.
"""
from __future__ import annotations

from app.db.base import Base
from app.db.models.companies import (
    Company,
    CompanyAlias,
    CompanyEnrichment,
    Contact,
)
from app.db.models.crm import Outreach, SalesFeedback
from app.db.models.events import EventSource, GovernmentEvent
from app.db.models.opportunities import (
    LeadScore,
    Opportunity,
    OpportunityEvidence,
    SalesBrief,
)
from app.db.models.ops import AuditLog, ProcessingJob
from app.db.models.sources import GovernmentSource, RawDocument
from app.db.models.tenancy import (
    Organization,
    Product,
    TargetSector,
    User,
    product_target_sectors,
)

__all__ = [
    "Base",
    "Organization",
    "User",
    "TargetSector",
    "Product",
    "product_target_sectors",
    "GovernmentSource",
    "RawDocument",
    "GovernmentEvent",
    "EventSource",
    "Company",
    "CompanyAlias",
    "CompanyEnrichment",
    "Contact",
    "Opportunity",
    "OpportunityEvidence",
    "LeadScore",
    "SalesBrief",
    "Outreach",
    "SalesFeedback",
    "ProcessingJob",
    "AuditLog",
]
