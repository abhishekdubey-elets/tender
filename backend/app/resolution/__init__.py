"""PART B — Company entity resolution.

Normalizes company-name variations ("M/s ABC Technologies Pvt Ltd", "ABC
Technologies Private Limited", "ABC Technologies Ltd.") into one canonical
company entity — but only when evidence supports it. Two companies are never
merged solely because their names are similar: a merge requires an identity
signal (matching registration id or domain) or exact canonical-name equality,
and a registration-id conflict blocks a merge outright.
"""
from __future__ import annotations

from app.resolution.matcher import (
    CompanyMatcher,
    CompanyObservation,
    CompanyRecord,
    MatchDecision,
)
from app.resolution.normalize import NameForms, normalize_company_name, normalize_domain
from app.resolution.service import (
    CompanyResolver,
    CompanyStore,
    InMemoryCompanyProvider,
    InMemoryCompanyStore,
    ResolutionResult,
)

__all__ = [
    "normalize_company_name",
    "normalize_domain",
    "NameForms",
    "CompanyMatcher",
    "CompanyObservation",
    "CompanyRecord",
    "MatchDecision",
    "CompanyResolver",
    "ResolutionResult",
    "CompanyStore",
    "InMemoryCompanyStore",
    "InMemoryCompanyProvider",
]
