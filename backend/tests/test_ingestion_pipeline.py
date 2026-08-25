"""End-to-end runner tests: idempotency, robots-skip, parse-failure handling.

These also demonstrate the extensibility guarantee: a brand-new adapter
(`_FakeAdapter`, defined only in this test) runs through the *unmodified*
IngestionRunner purely via the SourceAdapter interface.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import ClassVar

import httpx

from app.db.enums import GovSourceType
from app.ingestion.base import SourceAdapter
from app.ingestion.http_client import HttpClient
from app.ingestion.pipeline import IngestionRunner
from app.ingestion.storage import InMemorySink
from app.ingestion.types import DiscoveredItem
from tests.ing_util import allow_all_robots, make_client


class _FakeAdapter(SourceAdapter):
    name = "Fake Source"
    source_type = GovSourceType.other
    base_url = "https://data.example.gov.in/"

    urls: ClassVar[list[str]] = []

    def discover(self, client: HttpClient) -> Iterator[DiscoveredItem]:
        for url in self.urls:
            yield DiscoveredItem(url=url)


def _make(urls: list[str], handler) -> tuple[IngestionRunner, InMemorySink, _FakeAdapter]:
    client = make_client(handler)
    sink = InMemorySink()
    runner = IngestionRunner(client, sink)
    adapter = _FakeAdapter()
    adapter.urls = urls
    return runner, sink, adapter


def test_pipeline_stores_and_is_idempotent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = allow_all_robots(request)
        if robots is not None:
            return robots
        if request.url.path == "/a":
            return httpx.Response(200, text="<html><body>Award A</body></html>",
                                  headers={"content-type": "text/html"})
        return httpx.Response(200, json={"awardee": "Acme"},
                              headers={"content-type": "application/json"})

    urls = ["https://data.example.gov.in/a", "https://data.example.gov.in/b"]
    runner, sink, adapter = _make(urls, handler)

    r1 = runner.run(adapter)
    assert (r1.discovered, r1.fetched, r1.stored) == (2, 2, 0 + 2)
    assert len(sink) == 2

    # Re-running the same source stores nothing new (idempotent by content hash).
    r2 = runner.run(adapter)
    assert r2.fetched == 2
    assert r2.stored == 0
    assert r2.skipped_duplicate == 2
    assert len(sink) == 2


def test_pipeline_skips_robots_disallowed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})

    urls = ["https://data.example.gov.in/private/x", "https://data.example.gov.in/public/y"]
    runner, sink, adapter = _make(urls, handler)

    report = runner.run(adapter)
    assert report.skipped_robots == 1
    assert report.stored == 1
    assert len(sink) == 1


def test_pipeline_stores_raw_even_when_parse_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = allow_all_robots(request)
        if robots is not None:
            return robots
        # Declared JSON but invalid body -> parse fails, raw must still persist.
        return httpx.Response(200, content=b"{not valid json",
                              headers={"content-type": "application/json"})

    runner, sink, adapter = _make(["https://data.example.gov.in/broken"], handler)
    report = runner.run(adapter)
    assert report.stored == 1
    assert report.parse_failures == 1
    assert len(sink) == 1
    # Raw bytes preserved; no parse result.
    record = next(iter(sink.records.values()))
    assert record.document.content == b"{not valid json"
    assert record.parsed is None


def test_preserves_source_url_and_timestamp() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = allow_all_robots(request)
        if robots is not None:
            return robots
        return httpx.Response(200, text="hi", headers={"content-type": "text/plain"})

    url = "https://data.example.gov.in/doc"
    runner, sink, adapter = _make([url], handler)
    runner.run(adapter)
    record = next(iter(sink.records.values()))
    assert record.document.source_url == url
    assert record.document.fetched_at is not None
