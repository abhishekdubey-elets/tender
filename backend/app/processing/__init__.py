"""Document-processing layer.

Turns a raw downloaded source file into a normalized document:

    source file → validate → classify → extract text → OCR (when required)
                → extract metadata → NormalizedDocument

Design guarantees:
  * originals are preserved (the processor never mutates input bytes);
  * every document is hashed (sha256 + md5) and duplicates are detectable;
  * the extraction method and (where applicable) confidence are recorded;
  * malformed documents are never silently dropped — they yield a FAILED
    outcome with a reason, and the raw bytes are still persisted;
  * processing is retryable via ``processing_jobs`` rows.
"""
from __future__ import annotations

from app.processing.pipeline import DocumentProcessor
from app.processing.types import (
    Classification,
    DocClass,
    ExtractionResult,
    NormalizedDocument,
    ProcessingOutcome,
    ProcessingStatus,
    SourceFile,
    ValidationResult,
)

__all__ = [
    "DocumentProcessor",
    "SourceFile",
    "ValidationResult",
    "Classification",
    "ExtractionResult",
    "NormalizedDocument",
    "ProcessingOutcome",
    "ProcessingStatus",
    "DocClass",
]
