"""Metadata-extraction stage.

Extractors already pull format-specific metadata (PDF info dict, DOCX core
properties, XLSX sheet names, HTML title). This stage normalizes that and fills
sensible fallbacks (e.g. a title derived from the filename / URL) so downstream
consumers get a consistent shape.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from app.processing.types import Classification, DocumentMetadata, ExtractionResult, SourceFile


def _url_title(url: str) -> str | None:
    path = urlsplit(url).path
    segment = path.rstrip("/").rsplit("/", 1)[-1]
    return segment or None


def finalize_metadata(
    source: SourceFile, classification: Classification, extraction: ExtractionResult
) -> DocumentMetadata:
    meta = extraction.metadata
    if not meta.title:
        meta.title = source.filename or _url_title(source.source_url)
    meta.extra.setdefault("doc_class", classification.doc_class.value)
    return meta
