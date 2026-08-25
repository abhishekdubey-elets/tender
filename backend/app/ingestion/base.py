"""The SourceAdapter interface — the single extension point of the framework.

Every government source is one ``SourceAdapter`` subclass. It declares its
identity (name / type / URL) and its rate-limit policy, and implements two
methods:

    discover(client) -> Iterator[DiscoveredItem]   # the discovery method
    fetch(client, item) -> FetchedDocument         # the fetch method

Pagination, when applicable, is expressed inside ``discover`` (a generator that
keeps yielding across pages). Rate limiting and retries are declared here and
enforced by the shared HttpClient, so adapters never re-implement them. A
default ``fetch`` covers the common cases; adapters override it only when they
already hold the content (RSS/JSON) or need special handling.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import ClassVar

from app.db.enums import GovSourceType
from app.ingestion.http_client import HttpClient, HttpResponse
from app.ingestion.rate_limiter import RateLimitConfig
from app.ingestion.retry import RetryPolicy
from app.ingestion.types import DiscoveredItem, DocumentMetadata, FetchedDocument


class SourceAdapter(ABC):
    # --- identity (override as class attributes) ---
    name: ClassVar[str]
    source_type: ClassVar[GovSourceType]
    base_url: ClassVar[str]

    # --- policy ---
    rate_limit: ClassVar[RateLimitConfig] = RateLimitConfig()
    retry_policy: ClassVar[RetryPolicy | None] = None
    # Hint used to select a parser when the MIME type is ambiguous.
    parser_hint: ClassVar[str | None] = None
    # Set ``abstract = True`` directly on a generic intermediate (e.g. RSSAdapter)
    # to exempt it from the identity check. Not inherited (read from __dict__).
    abstract: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("abstract", False):
            return
        # Concrete adapters must declare identity; abstract intermediates need not.
        if not getattr(cls, "__abstractmethods__", None):
            for attr in ("name", "source_type", "base_url"):
                if not hasattr(cls, attr):
                    raise TypeError(f"{cls.__name__} must define class attribute '{attr}'")

    # ------------------------------------------------------------------ #
    # Required: discovery
    # ------------------------------------------------------------------ #
    @abstractmethod
    def discover(self, client: HttpClient) -> Iterator[DiscoveredItem]:
        """Yield pointers to documents. Implement pagination here."""
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Fetch (default implementation; override when needed)
    # ------------------------------------------------------------------ #
    def fetch(self, client: HttpClient, item: DiscoveredItem) -> FetchedDocument:
        if item.payload is not None:
            content, content_type = self.serialize_payload(item)
            return FetchedDocument(
                source_name=self.name,
                source_type=self.source_type.value,
                source_url=item.url,
                content=content,
                metadata=DocumentMetadata(
                    content_type=content_type,
                    title=item.title,
                    published_at=item.published_at,
                    source_ref=item.source_ref,
                ),
            )
        resp = client.get(item.url)
        return self._document_from_response(item, resp)

    # ------------------------------------------------------------------ #
    # Helpers available to subclasses
    # ------------------------------------------------------------------ #
    def serialize_payload(self, item: DiscoveredItem) -> tuple[bytes, str]:
        """Turn in-hand discovery payload into stored bytes. JSON by default."""
        return (
            json.dumps(item.payload, ensure_ascii=False, default=str, sort_keys=True).encode("utf-8"),
            "application/json",
        )

    def _document_from_response(self, item: DiscoveredItem, resp: HttpResponse) -> FetchedDocument:
        headers = resp.headers
        return FetchedDocument(
            source_name=self.name,
            source_type=self.source_type.value,
            source_url=item.url,
            canonical_url=resp.url if resp.url != item.url else None,
            content=resp.content,
            metadata=DocumentMetadata(
                content_type=headers.get("content-type", "").split(";")[0].strip() or None,
                http_status=resp.status,
                byte_size=len(resp.content),
                etag=headers.get("etag"),
                last_modified=headers.get("last-modified"),
                title=item.title,
                published_at=item.published_at,
                source_ref=item.source_ref,
                headers=headers,
            ),
        )
