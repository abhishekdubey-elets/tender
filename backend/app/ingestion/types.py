"""Domain objects that flow through ingestion.

These are deliberately independent of both the HTTP layer and the database, so
adapters, parsers and sinks can be tested in isolation with plain objects.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(slots=True)
class DiscoveredItem:
    """A pointer produced by an adapter's discovery step.

    ``url`` is the canonical location of the item. ``payload`` optionally carries
    data already obtained during discovery (e.g. an RSS entry or an API record),
    so ``fetch`` need not make a second request when the content is already in
    hand.
    """

    url: str
    source_ref: str | None = None          # stable id within the source, if any
    title: str | None = None
    published_at: datetime | None = None
    content_type_hint: str | None = None    # e.g. "rss", "json", "pdf"
    payload: Any | None = None              # pre-fetched content, if available
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DocumentMetadata:
    """Metadata captured about a fetched document."""

    content_type: str | None = None         # MIME type
    http_status: int | None = None
    byte_size: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    title: str | None = None
    published_at: datetime | None = None
    language: str | None = None
    source_ref: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FetchedDocument:
    """A raw document as fetched from a source — the authoritative artefact.

    ``source_url`` and ``fetched_at`` are always populated (provenance must never
    be lost). ``content_hash`` makes ingestion idempotent.
    """

    source_name: str
    source_type: str
    source_url: str
    content: bytes
    fetched_at: datetime = field(default_factory=utcnow)
    canonical_url: str | None = None
    content_hash: str = ""
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = sha256_hex(self.content)
        if self.metadata.byte_size is None:
            self.metadata.byte_size = len(self.content)


@dataclass(slots=True)
class ParsedContent:
    """The result of parsing a fetched document. Derived, never authoritative."""

    parser_name: str
    text: str | None = None
    structured: Any | None = None
    title: str | None = None
    published_at: datetime | None = None
    language: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
