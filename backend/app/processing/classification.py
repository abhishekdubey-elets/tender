"""Document classification → a :class:`DocClass`.

Classification is by content (magic bytes) first; the declared MIME / filename
only break ties. PDFs are classified as ``pdf`` here; whether a PDF is actually
*scanned* (image-only) is decided during extraction, when the text layer is
inspected.
"""
from __future__ import annotations

from app.processing.sniff import sniff
from app.processing.types import Classification, SourceFile


def classify(source: SourceFile) -> Classification:
    result = sniff(source.content, declared_mime=source.declared_mime, filename=source.filename)
    warnings = []
    if result.note in ("legacy_ole", "zip"):
        warnings.append(f"sniff_note:{result.note}")
    # Confidence: high for distinctive binary/text signatures, lower when we had
    # to fall back to a generic text guess.
    confidence = 0.7 if result.note else 0.95
    return Classification(
        doc_class=result.doc_class,
        detected_mime=result.mime,
        confidence=confidence,
        warnings=warnings,
    )
