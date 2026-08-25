"""Contact discovery.

Finds business-context decision-maker contacts for a company via injected
provider adapters (people-search / email-finder APIs — never login-scraping or
CAPTCHA circumvention). Candidates are de-duplicated across sources, ranked by
fit to the target roles, and passed through a DPDP compliance gate that records
a lawful basis, drops do-not-contact records, and suppresses personal emails.
Every contact keeps its source and confidence.
"""
from __future__ import annotations

from app.contacts.compliance import CompliancePolicy, apply_compliance
from app.contacts.service import ContactDiscoveryService
from app.contacts.types import ContactCandidate, ContactQuery, DiscoveryResult

__all__ = [
    "ContactDiscoveryService",
    "ContactCandidate",
    "ContactQuery",
    "DiscoveryResult",
    "CompliancePolicy",
    "apply_compliance",
]
