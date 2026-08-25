"""Adapter tests: RSS discovery/fetch, JSON API pagination, registry."""
from __future__ import annotations

import json
from typing import Any, ClassVar

import httpx

from app.db.enums import GovSourceType
from app.ingestion.adapters.json_api_adapter import JSONApiAdapter
from app.ingestion.adapters.rss_adapter import RSSAdapter
from app.ingestion.registry import list_adapters
from tests.ing_util import allow_all_robots, make_client
from tests.test_ingestion_parsers import RSS_XML


class _FeedAdapter(RSSAdapter):
    name = "Test Feed"
    source_type = GovSourceType.pib
    base_url = "https://feeds.example.gov.in/"
    feed_url = "https://feeds.example.gov.in/feed"


def test_rss_adapter_discovers_and_fetches_entries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = allow_all_robots(request)
        if robots is not None:
            return robots
        if request.url.path == "/feed":
            return httpx.Response(200, content=RSS_XML, headers={"content-type": "application/rss+xml"})
        return httpx.Response(404)

    client = make_client(handler)
    adapter = _FeedAdapter()
    items = list(adapter.discover(client))
    assert len(items) == 2
    assert items[0].url == "https://g.gov.in/a"
    assert items[0].title == "Award A"

    # fetch uses the in-hand payload (no second network hit) and preserves URL/ts.
    doc = adapter.fetch(client, items[0])
    assert doc.source_url == "https://g.gov.in/a"
    assert doc.source_type == "pib"
    assert doc.content_hash  # populated
    assert doc.fetched_at is not None
    assert doc.metadata.content_type == "application/json"
    assert json.loads(doc.content)["title"] == "Award A"


class _PagedApiAdapter(JSONApiAdapter):
    name = "Test Paged API"
    source_type = GovSourceType.api
    base_url = "https://api.example.gov.in/"
    page_size: ClassVar[int] = 2
    records_path: ClassVar[tuple[str, ...]] = ("records",)

    def build_page_url(self, offset: int, limit: int) -> str:
        return f"https://api.example.gov.in/data?offset={offset}&limit={limit}"

    def record_url(self, record: Any, offset: int, index: int) -> str:
        return f"https://api.example.gov.in/data#row={offset + index}"


def test_json_api_adapter_paginates() -> None:
    pages = {
        0: {"records": [{"id": "r0"}, {"id": "r1"}]},   # full page -> continue
        2: {"records": [{"id": "r2"}]},                  # short page -> stop
    }

    def handler(request: httpx.Request) -> httpx.Response:
        robots = allow_all_robots(request)
        if robots is not None:
            return robots
        offset = int(request.url.params.get("offset", "0"))
        return httpx.Response(200, json=pages.get(offset, {"records": []}))

    client = make_client(handler)
    adapter = _PagedApiAdapter()
    items = list(adapter.discover(client))
    assert [i.source_ref for i in items] == ["r0", "r1", "r2"]
    assert items[0].url == "https://api.example.gov.in/data#row=0"


def test_concrete_sources_are_registered() -> None:
    registry = list_adapters()
    assert "PIB Press Releases" in registry
    assert "data.gov.in Open Data" in registry
