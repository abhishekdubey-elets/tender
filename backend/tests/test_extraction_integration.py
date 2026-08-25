"""Integration: ingestion → processing → extraction wired together."""
from __future__ import annotations

from collections.abc import Iterator
from typing import ClassVar

import httpx

from app.db.enums import GovSourceType
from app.extraction.integration import (
    DocumentPipelineResult,
    make_ingestion_document_hook,
    run_document,
)
from app.extraction.llm import FakeLLMClient
from app.extraction.service import EventExtractionService
from app.extraction.types import ExtractionStatus
from app.ingestion.base import SourceAdapter
from app.ingestion.http_client import HttpClient
from app.ingestion.pipeline import IngestionRunner
from app.ingestion.storage import InMemorySink
from app.ingestion.types import DiscoveredItem, DocumentMetadata, FetchedDocument
from app.processing.pipeline import DocumentProcessor
from tests.ext_util import envelope, event, fixed_now
from tests.ing_util import allow_all_robots, make_client

HTML = (
    b"<html><body><p>Contract awarded to Acme Infra Pvt Ltd for smart city works.</p>"
    b"</body></html>"
)


def _fetched() -> FetchedDocument:
    return FetchedDocument(
        source_name="PIB", source_type="pib",
        source_url="https://pib.gov.in/pr/1", content=HTML,
        metadata=DocumentMetadata(content_type="text/html"),
    )


def _service() -> EventExtractionService:
    resp = envelope(event(
        event_type="contract_award",
        entities=[{"name": "Acme Infra Pvt Ltd", "role": "awardee"}],
        evidence=[{"field": "entities[0].name", "snippet": "Acme Infra Pvt Ltd"}],
        confidence=0.85,
    ))
    return EventExtractionService(FakeLLMClient([resp]), now=fixed_now)


def test_run_document_processes_then_extracts() -> None:
    result = run_document(_fetched(), DocumentProcessor(), _service())
    assert result.outcome.is_success
    assert result.extraction is not None
    assert result.extraction.status is ExtractionStatus.succeeded
    assert result.extraction.events[0].entities[0].name == "Acme Infra Pvt Ltd"


class _OneDocAdapter(SourceAdapter):
    name = "One Doc"
    source_type = GovSourceType.pib
    base_url = "https://pib.gov.in/"
    urls: ClassVar[list[str]] = ["https://pib.gov.in/pr/1"]

    def discover(self, client: HttpClient) -> Iterator[DiscoveredItem]:
        for url in self.urls:
            yield DiscoveredItem(url=url)


def test_extraction_hook_runs_inside_ingestion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = allow_all_robots(request)
        if robots is not None:
            return robots
        return httpx.Response(200, content=HTML, headers={"content-type": "text/html"})

    results: list[DocumentPipelineResult] = []
    hook = make_ingestion_document_hook(DocumentProcessor(), _service(), results)
    runner = IngestionRunner(make_client(handler), InMemorySink(), on_document=hook)

    report = runner.run(_OneDocAdapter())
    assert report.stored == 1
    assert not report.errors
    # The document was processed and extracted as part of ingestion.
    assert len(results) == 1
    assert results[0].extraction is not None
    assert results[0].extraction.events[0].event_type == "contract_award"
