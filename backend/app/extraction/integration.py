"""Wiring the extraction service into the ingestion → processing pipeline.

``run_document`` chains the three stages for one document:
    FetchedDocument → SourceFile → NormalizedDocument → ExtractionResult

``make_ingestion_document_hook`` returns a callback suitable for
``IngestionRunner(on_document=...)``, so extraction runs as documents are
ingested. Persistence (``persist_events``) stays a separate, session-aware call.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.extraction.service import EventExtractionService
from app.extraction.types import ExtractionResult
from app.ingestion.types import FetchedDocument, ParsedContent
from app.processing.pipeline import DocumentProcessor
from app.processing.types import ProcessingOutcome, SourceFile


def source_file_from_fetched(fetched: FetchedDocument) -> SourceFile:
    return SourceFile(
        content=fetched.content,
        source_url=fetched.source_url,
        source_name=fetched.source_name,
        source_type=fetched.source_type,
        fetched_at=fetched.fetched_at,
        declared_mime=fetched.metadata.content_type,
    )


@dataclass(slots=True)
class DocumentPipelineResult:
    fetched: FetchedDocument
    outcome: ProcessingOutcome
    extraction: ExtractionResult | None = None


def run_document(
    fetched: FetchedDocument,
    processor: DocumentProcessor,
    service: EventExtractionService,
) -> DocumentPipelineResult:
    outcome = processor.process(source_file_from_fetched(fetched))
    extraction: ExtractionResult | None = None
    if outcome.normalized is not None and outcome.normalized.text:
        extraction = service.extract(outcome.normalized)
    return DocumentPipelineResult(fetched=fetched, outcome=outcome, extraction=extraction)


def make_ingestion_document_hook(
    processor: DocumentProcessor,
    service: EventExtractionService,
    results: list[DocumentPipelineResult],
) -> Callable[[FetchedDocument, ParsedContent | None], None]:
    """Build an ``on_document`` hook that processes + extracts each fetched
    document and appends the result to ``results``."""

    def hook(fetched: FetchedDocument, _parsed: ParsedContent | None) -> None:
        results.append(run_document(fetched, processor, service))

    return hook
