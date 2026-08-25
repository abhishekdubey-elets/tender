"""Generic RSS / Atom adapter.

Discovery fetches the feed once and yields one item per entry, carrying the
entry data as payload so ``fetch`` needs no second request (polite: one hit per
run for the whole feed). Each entry is stored as a JSON document that preserves
the entry's own link and publish timestamp.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from time import struct_time
from typing import ClassVar

from app.ingestion.base import SourceAdapter
from app.ingestion.http_client import HttpClient
from app.ingestion.types import DiscoveredItem


def _to_datetime(parsed: struct_time | None) -> datetime | None:
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc)


class RSSAdapter(SourceAdapter):
    abstract = True
    parser_hint = "json"  # entries are stored as JSON payloads

    feed_url: ClassVar[str]

    def discover(self, client: HttpClient) -> Iterator[DiscoveredItem]:
        import feedparser

        resp = client.get(self.feed_url)
        feed = feedparser.parse(resp.content)
        for entry in feed.get("entries", []):
            link = entry.get("link") or self.feed_url
            yield DiscoveredItem(
                url=link,
                source_ref=entry.get("id") or link,
                title=entry.get("title"),
                published_at=_to_datetime(entry.get("published_parsed")),
                content_type_hint="json",
                payload={
                    "title": entry.get("title"),
                    "link": link,
                    "summary": entry.get("summary"),
                    "published": entry.get("published"),
                    "id": entry.get("id"),
                },
            )
