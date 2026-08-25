"""The generic ingestion runner.

It drives *any* adapter through discover → fetch → (dedupe) → parse → store using
only the :class:`SourceAdapter` interface and a sink. Adding a new source never
requires changing this module.

Idempotency: documents are de-duplicated by content hash via the sink, so
re-running a source stores nothing new when content is unchanged.

Error handling: robots-disallowed and 404 items are skipped politely; fetch
errors are recorded and the run continues; a parse failure still stores the raw
document (provenance is never lost) with no parse result.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.ingestion.base import SourceAdapter
from app.ingestion.errors import (
    FetchError,
    NotFound,
    ParseError,
    RateLimited,
    RobotsDisallowed,
)
from app.ingestion.http_client import HttpClient
from app.ingestion.parsers import OcrEngine, PdfTextBackend, parse_document
from app.ingestion.storage import RawDocumentSink
from app.ingestion.types import FetchedDocument, ParsedContent

# Called after a document is stored — the extension point where downstream
# stages (document processing, event extraction) plug into ingestion.
OnDocument = Callable[[FetchedDocument, ParsedContent | None], None]


@dataclass
class IngestionReport:
    source_name: str
    discovered: int = 0
    fetched: int = 0
    stored: int = 0
    skipped_duplicate: int = 0
    skipped_robots: int = 0
    not_found: int = 0
    parse_failures: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)  # (url, message)

    @property
    def ok(self) -> bool:
        return not self.errors


class IngestionRunner:
    def __init__(
        self,
        client: HttpClient,
        sink: RawDocumentSink,
        *,
        pdf_text_backend: PdfTextBackend | None = None,
        ocr_engine: OcrEngine | None = None,
        max_items: int | None = None,
        on_document: OnDocument | None = None,
    ) -> None:
        self._client = client
        self._sink = sink
        self._pdf_text_backend = pdf_text_backend
        self._ocr_engine = ocr_engine
        self._max_items = max_items
        self._on_document = on_document

    def run(self, adapter: SourceAdapter) -> IngestionReport:
        report = IngestionReport(source_name=adapter.name)

        try:
            items = adapter.discover(self._client)
        except (RobotsDisallowed, NotFound, RateLimited, FetchError) as exc:
            report.errors.append((adapter.base_url, f"discovery failed: {exc}"))
            return report

        for item in items:
            if self._max_items is not None and report.fetched >= self._max_items:
                break
            report.discovered += 1

            try:
                document = adapter.fetch(self._client, item)
            except RobotsDisallowed:
                report.skipped_robots += 1
                continue
            except NotFound:
                report.not_found += 1
                continue
            except (RateLimited, FetchError) as exc:
                report.errors.append((item.url, str(exc)))
                continue

            report.fetched += 1

            # Idempotency: skip content we already have.
            if self._sink.exists(adapter.name, document.content_hash):
                report.skipped_duplicate += 1
                continue

            parsed = None
            try:
                parsed = parse_document(
                    document,
                    hint=adapter.parser_hint,
                    pdf_text_backend=self._pdf_text_backend,
                    ocr_engine=self._ocr_engine,
                )
            except ParseError as exc:
                report.parse_failures += 1
                report.errors.append((item.url, f"parse failed: {exc}"))

            # Raw document is stored regardless of parse outcome.
            self._sink.store(document, parsed)
            report.stored += 1

            # Downstream hook (processing + extraction) — failures here must not
            # abort ingestion of the remaining items.
            if self._on_document is not None:
                try:
                    self._on_document(document, parsed)
                except Exception as exc:  # noqa: BLE001 - isolate downstream errors
                    report.errors.append((item.url, f"on_document hook failed: {exc}"))

        return report
