"""The document-processing pipeline.

``DocumentProcessor.process`` runs, in order:

    hash → validate → (duplicate check) → classify → extract (+OCR) → metadata
         → NormalizedDocument

It never raises for a bad document: validation failures, unsupported formats and
extraction errors all become a FAILED :class:`ProcessingOutcome` carrying the
reason (the raw bytes are preserved by the caller/sink regardless). Scanned PDFs
with no OCR engine yield a NEEDS_OCR outcome so they can be retried later.
"""
from __future__ import annotations

from app.processing.classification import classify
from app.processing.dedup import DuplicateIndex
from app.processing.errors import ExtractionFailure, ProcessingError, UnsupportedDocumentError
from app.processing.extractors import ExtractionContext, get_extractor
from app.processing.hashing import compute_hashes
from app.processing.metadata import finalize_metadata
from app.processing.types import (
    NormalizedDocument,
    ProcessingOutcome,
    ProcessingStatus,
    SourceFile,
)
from app.processing.validation import validate


class DocumentProcessor:
    def __init__(
        self,
        *,
        context: ExtractionContext | None = None,
        duplicate_index: DuplicateIndex | None = None,
        max_bytes: int | None = None,
    ) -> None:
        self._ctx = context or ExtractionContext()
        self._dupes = duplicate_index
        self._max_bytes = max_bytes

    def process(self, source: SourceFile) -> ProcessingOutcome:
        hashes = compute_hashes(source.content)
        sha = hashes.sha256

        # 1. Validation — malformed/empty/oversize/unrecognized are failures,
        #    never silent drops.
        validation = (
            validate(source, max_bytes=self._max_bytes)
            if self._max_bytes is not None
            else validate(source)
        )
        if not validation.is_valid:
            return ProcessingOutcome(
                status=ProcessingStatus.failed,
                sha256=sha,
                error=validation.reason,
                error_kind="invalid_file",
                warnings=validation.warnings,
            )

        # 2. Duplicate detection (exact, by content hash).
        if self._dupes is not None:
            existing = self._dupes.get(sha)
            if existing is not None:
                return ProcessingOutcome(
                    status=ProcessingStatus.succeeded,
                    sha256=sha,
                    duplicate_of=existing,
                    warnings=[f"duplicate_of:{existing}"],
                )

        # 3. Classification.
        classification = classify(source)

        # 4. Extraction (+ OCR when required).
        try:
            extractor = get_extractor(classification.doc_class)
            extraction = extractor(source, self._ctx)
        except UnsupportedDocumentError as exc:
            return ProcessingOutcome(
                status=ProcessingStatus.failed, sha256=sha, error=str(exc), error_kind=exc.kind
            )
        except ExtractionFailure as exc:
            return ProcessingOutcome(
                status=ProcessingStatus.failed, sha256=sha, error=str(exc), error_kind=exc.kind
            )
        except ProcessingError as exc:  # any other typed processing error
            return ProcessingOutcome(
                status=ProcessingStatus.failed, sha256=sha, error=str(exc), error_kind=exc.kind
            )

        # 5. Metadata.
        metadata = finalize_metadata(source, classification, extraction)

        warnings = [*validation.warnings, *classification.warnings, *extraction.warnings]
        normalized = NormalizedDocument(
            source_url=source.source_url,
            source_name=source.source_name,
            source_type=source.source_type,
            fetched_at=source.fetched_at,
            sha256=sha,
            md5=hashes.md5,
            byte_size=hashes.byte_size,
            doc_class=extraction.doc_class_final,
            detected_mime=classification.detected_mime,
            declared_mime=source.declared_mime,
            extraction_method=extraction.method,
            extraction_confidence=extraction.confidence,
            ocr_used=extraction.ocr_used,
            text=extraction.text,
            metadata=metadata,
            warnings=warnings,
        )

        if self._dupes is not None:
            self._dupes.add(sha, sha)  # register first occurrence

        status = ProcessingStatus.needs_ocr if extraction.needs_ocr else ProcessingStatus.succeeded
        return ProcessingOutcome(
            status=status, normalized=normalized, sha256=sha, warnings=warnings
        )
