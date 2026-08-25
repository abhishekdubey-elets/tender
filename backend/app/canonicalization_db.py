"""Database adapters for deduplication + company resolution, and the high-level
``persist_canonical`` that ties extraction output to the schema.

This is the only place the two matching systems touch the ORM; the packages
themselves stay database-free.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.canonicalization import (
    canonicalize_extracted,
    observation_from_entity,
    primary_awardee_entity,
)
from app.dedup.fingerprint import EventFingerprint
from app.dedup.matcher import EventMatcher, HashingEmbedder
from app.dedup.service import EventDeduplicator
from app.db.enums import AliasSource, AliasType, ExtractionStatus
from app.db.models import Company, CompanyAlias, GovernmentEvent, RawDocument
from app.extraction.mapping import build_event_source, build_government_event
from app.extraction.schema import ExtractedEvent
from app.extraction.types import ExtractionResult
from app.resolution.matcher import CompanyMatcher, CompanyObservation, CompanyRecord
from app.resolution.service import CompanyResolver


# --- event dedup adapters ---------------------------------------------------
def fingerprint_from_orm(ge: GovernmentEvent) -> EventFingerprint:
    attrs = ge.attributes or {}
    ids = [ge.reference_number, *(attrs.get("identifiers", {}) or {}).values()]
    return EventFingerprint.build(
        identifiers=[i for i in ids if i],
        buyer=ge.buyer_name,
        company=ge.awardee_name,
        value=ge.value_amount,
        event_date=ge.event_date,
        event_type=attrs.get("extraction_event_type") or ge.event_type.value,
        text=" ".join(filter(None, [ge.title, ge.summary])) or None,
    )


class DbEventCandidateProvider:
    def __init__(self, session: Session) -> None:
        self._session = session

    def candidates(self, fp: EventFingerprint) -> list[tuple[Any, EventFingerprint]]:
        filters = []
        if fp.event_date is not None:
            filters.append(GovernmentEvent.event_date == fp.event_date)
        if fp.company is not None:
            filters.append(GovernmentEvent.awardee_name.ilike(f"%{fp.company}%"))
        if fp.identifiers:
            filters.append(GovernmentEvent.reference_number.isnot(None))
        if not filters:
            return []
        rows = self._session.scalars(
            select(GovernmentEvent).where(or_(*filters)).limit(50)
        ).all()
        # Only keep those that share a normalized identifier or are date/company
        # plausible; the matcher makes the final decision.
        out = []
        for ge in rows:
            out.append((ge.id, fingerprint_from_orm(ge)))
        return out


class DbEventStore:
    def __init__(self, session: Session, raw_document: RawDocument, model: str) -> None:
        self._session = session
        self._raw = raw_document
        self._model = model

    def create_canonical(self, payload: ExtractedEvent, fingerprint: EventFingerprint, context: Any) -> Any:
        ge = build_government_event(payload)
        self._session.add(ge)
        es = build_event_source(payload, ge, self._raw, self._model)
        self._session.add(es)
        self._session.flush()
        return ge.id

    def link_source(self, ref: Any, payload: ExtractedEvent, context: Any) -> None:
        ge = self._session.get(GovernmentEvent, ref)
        es = build_event_source(payload, ge, self._raw, self._model)
        es.is_primary = False                     # additional evidence, not primary
        self._session.add(es)
        ge.last_seen_at = datetime.now(timezone.utc)
        self._session.flush()


# --- company resolution adapters -------------------------------------------
def _record_from_company(session: Session, company: Company) -> CompanyRecord:
    aliases = session.scalars(
        select(CompanyAlias.normalized_alias).where(CompanyAlias.company_id == company.id)
    ).all()
    return CompanyRecord(
        ref=company.id,
        canonical_name=company.canonical_name,
        core=company.normalized_name,
        aliases_full=set(aliases),
        cin=company.cin, gstin=company.gstin, pan=company.pan,
        domain=company.domain, state=company.hq_state, city=company.hq_city,
    )


class DbCompanyProvider:
    def __init__(self, session: Session) -> None:
        self._session = session

    def candidates(self, obs: CompanyObservation) -> list[CompanyRecord]:
        forms = obs.forms
        filters = [Company.normalized_name == forms.core]
        if obs.cin:
            filters.append(Company.cin == obs.cin)
        if obs.gstin:
            filters.append(Company.gstin == obs.gstin)
        if obs.domain:
            filters.append(Company.domain == obs.domain)
        companies = set(self._session.scalars(select(Company).where(or_(*filters))).all())
        # alias match
        alias_hits = self._session.scalars(
            select(Company).join(CompanyAlias).where(CompanyAlias.normalized_alias == forms.normalized_full)
        ).all()
        companies.update(alias_hits)
        return [_record_from_company(self._session, c) for c in companies]


class DbCompanyStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_company(self, obs: CompanyObservation, *, possible_duplicate_of=None, evidence=None) -> Any:
        forms = obs.forms
        company = Company(
            canonical_name=forms.display,
            normalized_name=forms.core,
            cin=obs.cin, gstin=obs.gstin, pan=obs.pan,
            website=obs.website, domain=obs.domain,
            hq_state=obs.state, hq_city=obs.city,
        )
        self._session.add(company)
        self._session.flush()
        self._add_alias_row(company.id, obs)
        return company.id

    def add_alias(self, ref: Any, obs: CompanyObservation) -> None:
        self._add_alias_row(ref, obs)

    def merge_attrs(self, ref: Any, obs: CompanyObservation) -> None:
        company = self._session.get(Company, ref)
        company.cin = company.cin or obs.cin
        company.gstin = company.gstin or obs.gstin
        company.pan = company.pan or obs.pan
        company.domain = company.domain or obs.domain
        company.hq_state = company.hq_state or obs.state
        company.hq_city = company.hq_city or obs.city
        self._session.flush()

    def _add_alias_row(self, company_id: Any, obs: CompanyObservation) -> None:
        normalized = obs.forms.normalized_full
        exists = self._session.scalar(
            select(CompanyAlias.id).where(
                CompanyAlias.company_id == company_id,
                CompanyAlias.normalized_alias == normalized,
            )
        )
        if exists:
            return
        self._session.add(CompanyAlias(
            company_id=company_id,
            alias=obs.raw_name,
            normalized_alias=normalized,
            alias_type=AliasType.as_reported,
            source=AliasSource.government_event,
            confidence=1.0,
        ))
        self._session.flush()


# --- high-level entry point -------------------------------------------------
def persist_canonical(
    session: Session, extraction_result: ExtractionResult, raw_document: RawDocument
) -> list[Any]:
    """Deduplicate + resolve + persist all events from one extraction.

    Returns the canonical government_event ids the document contributed to.
    """
    model = extraction_result.meta.model
    deduper = EventDeduplicator(
        EventMatcher(embedder=HashingEmbedder()),
        DbEventCandidateProvider(session),
        DbEventStore(session, raw_document, model),
    )
    resolver = CompanyResolver(CompanyMatcher(), DbCompanyProvider(session), DbCompanyStore(session))

    # Dedup only here; resolution + company linking is done below so we can attach
    # the resolved company to the canonical event.
    report = canonicalize_extracted(
        extraction_result.events, deduplicator=deduper, resolver=None
    )

    canonical_ids: list[Any] = []
    for event, decision in zip(extraction_result.events, report.dedup, strict=True):
        canonical_ids.append(decision.ref)
        ge = session.get(GovernmentEvent, decision.ref)
        entity = primary_awardee_entity(event)
        if ge is not None and entity is not None and ge.company_id is None:
            res = resolver.resolve(observation_from_entity(entity, event))
            ge.company_id = res.ref
            ge.company_resolution_confidence = res.confidence

    raw_document.extraction_status = ExtractionStatus.extracted
    session.flush()
    return canonical_ids
