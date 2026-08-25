"""DPDP-aware compliance gate for discovered contacts.

Records a lawful basis, honours a do-not-contact list, and (by default)
suppresses personal/free-email addresses so only business-context contacts are
retained. This is a design boundary, not an afterthought.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.contacts.types import ContactCandidate, is_free_email, normalize_name

_DEFAULT_BASIS = "legitimate interest: business-context professional outreach (India DPDP)"


@dataclass(slots=True)
class CompliancePolicy:
    allow_personal_email: bool = False
    do_not_contact_emails: set[str] = field(default_factory=set)
    do_not_contact_names: set[str] = field(default_factory=set)
    default_lawful_basis: str = _DEFAULT_BASIS


def apply_compliance(candidate: ContactCandidate, policy: CompliancePolicy) -> ContactCandidate | None:
    """Return the (possibly modified) candidate, or None if it must be dropped."""
    email_l = candidate.email.lower() if candidate.email else None
    if email_l and email_l in policy.do_not_contact_emails:
        return None
    if normalize_name(candidate.name) in {normalize_name(n) for n in policy.do_not_contact_names}:
        return None

    if not candidate.lawful_basis:
        candidate.lawful_basis = policy.default_lawful_basis

    # Suppress personal emails unless explicitly allowed; keep the contact (via
    # its professional profile) but without the personal address.
    if candidate.email and is_free_email(candidate.email) and not policy.allow_personal_email:
        candidate.email = None
        candidate.verified = False
        candidate.confidence = min(candidate.confidence, 0.5)
        candidate.lawful_basis += " | personal email suppressed"

    return candidate
