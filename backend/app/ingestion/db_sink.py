"""SQLAlchemy-backed sink: persists fetched documents as ``raw_documents`` rows.

Kept in its own module so the rest of the ingestion framework (and its tests)
never needs a database. The government source is resolved get-or-create by a
slug derived from the source name, so ingestion can run before an operator has
manually catalogued the source.

Idempotency is enforced both here (``exists``) and by the DB unique constraint
``(government_source_id, content_hash)``.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AccessMethod, GovSourceType, ParseStatus
from app.db.models import GovernmentSource, RawDocument
from app.ingestion.storage import FilesystemRawStorage
from app.ingestion.types import FetchedDocument, ParsedContent

_TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xml", "application/rss")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:120] or "source"


class SqlAlchemySink:
    def __init__(self, session: Session, raw_storage: FilesystemRawStorage | None = None) -> None:
        self._session = session
        self._raw_storage = raw_storage
        self._source_cache: dict[str, GovernmentSource] = {}

    # -- source resolution --------------------------------------------------
    def _get_or_create_source(self, document: FetchedDocument) -> GovernmentSource:
        slug = slugify(document.source_name)
        if slug in self._source_cache:
            return self._source_cache[slug]
        source = self._session.scalar(select(GovernmentSource).where(GovernmentSource.slug == slug))
        if source is None:
            parts = urlsplit(document.source_url)
            base_url = f"{parts.scheme}://{parts.netloc}/" if parts.netloc else document.source_url
            try:
                source_type = GovSourceType(document.source_type)
            except ValueError:
                source_type = GovSourceType.other
            source = GovernmentSource(
                name=document.source_name,
                slug=slug,
                source_type=source_type,
                base_url=base_url,
                access_method=AccessMethod.api,
            )
            self._session.add(source)
            self._session.flush()
        self._source_cache[slug] = source
        return source

    # -- sink protocol ------------------------------------------------------
    def exists(self, source_name: str, content_hash: str) -> bool:
        slug = slugify(source_name)
        source = self._session.scalar(
            select(GovernmentSource).where(GovernmentSource.slug == slug)
        )
        if source is None:
            return False
        found = self._session.scalar(
            select(RawDocument.id).where(
                RawDocument.government_source_id == source.id,
                RawDocument.content_hash == content_hash,
            )
        )
        return found is not None

    def store(self, document: FetchedDocument, parsed: ParsedContent | None) -> str:
        source = self._get_or_create_source(document)
        mime = document.metadata.content_type or ""
        is_text = any(mime.startswith(p) for p in _TEXT_MIME_PREFIXES)

        raw_content: str | None = None
        storage_backend: str | None = None
        storage_path: str | None = None
        if is_text:
            raw_content = document.content.decode("utf-8", errors="replace")
        elif self._raw_storage is not None:
            storage_path = self._raw_storage.save(document)
            storage_backend = "filesystem"

        if parsed is not None and (parsed.text or parsed.structured is not None):
            parse_status = ParseStatus.parsed
        elif parsed is None:
            parse_status = ParseStatus.pending
        else:
            parse_status = ParseStatus.failed

        row = RawDocument(
            government_source_id=source.id,
            source_url=document.source_url,
            canonical_url=document.canonical_url,
            content_hash=document.content_hash,
            fetched_at=document.fetched_at,
            http_status=document.metadata.http_status,
            mime_type=mime or None,
            byte_size=document.metadata.byte_size,
            language=parsed.language if parsed else None,
            title=(parsed.title if parsed and parsed.title else document.metadata.title),
            raw_content=raw_content,
            storage_backend=storage_backend,
            storage_path=storage_path,
            parsed_text=parsed.text if parsed else None,
            parse_status=parse_status,
            meta={"source_ref": document.metadata.source_ref} if document.metadata.source_ref else None,
        )
        self._session.add(row)
        self._session.flush()
        return str(row.id)
