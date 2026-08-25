"""Persist discovered contacts into the ``contacts`` table."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contacts.types import ContactCandidate, DiscoveryResult
from app.db.enums import ContactSource, Seniority
from app.db.models import Contact

_SOURCE_MAP = {"directory": ContactSource.linkedin, "provider": ContactSource.apollo}


def _seniority(value: str | None) -> Seniority:
    try:
        return Seniority(value) if value else Seniority.unknown
    except ValueError:
        return Seniority.unknown


def _source(name: str) -> ContactSource:
    for token, enum_val in _SOURCE_MAP.items():
        if token in name:
            return enum_val
    return ContactSource.other


def persist_contacts(session: Session, company_id: Any, result: DiscoveryResult) -> list[Contact]:
    rows: list[Contact] = []
    for c in result.contacts:
        # Idempotency: skip if a contact with the same email already exists.
        if c.email:
            existing = session.scalar(
                select(Contact.id).where(Contact.company_id == company_id, Contact.email == c.email)
            )
            if existing:
                continue
        row = Contact(
            company_id=company_id,
            full_name=c.name,
            title=c.title,
            seniority=_seniority(c.seniority),
            department=c.department,
            email=c.email,
            phone=c.phone,
            linkedin_url=c.linkedin_url,
            source=_source(c.source_name),
            source_url=c.source_url,
            lawful_basis=c.lawful_basis,
            confidence=c.confidence,
            is_verified=c.verified,
            do_not_contact=c.do_not_contact,
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows
