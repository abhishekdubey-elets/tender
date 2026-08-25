"""Domain objects and enums for the document-processing layer.

These are independent of the database and of any heavy parsing library, so the
whole pipeline is unit-testable with plain objects.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class DocClass(str, enum.Enum):
    html = "html"
    pdf = "pdf"                 # PDF with a usable text layer
    pdf_scanned = "pdf_scanned" # image-only PDF → needs OCR
    docx = "docx"
    doc = "doc"                 # legacy binary Word (best-effort / unsupported)
    xlsx = "xlsx"
    xls = "xls"                 # legacy binary Excel (best-effort / unsupported)
    json = "json"
    text = "text"
    unknown = "unknown"


class ProcessingStatus(str, enum.Enum):
    succeeded = "succeeded"
    failed = "failed"
    needs_ocr = "needs_ocr"     # scanned doc but no OCR engine available


# Extraction-method identifiers (stored so we know *how* text was produced).
class Method:
    HTML_BS4 = "html.beautifulsoup"
    PDF_TEXT = "pdf.text.pypdf"
    PDF_OCR = "pdf.ocr.tesseract"
    DOCX = "docx.python-docx"
    XLSX = "xlsx.openpyxl"
    JSON = "json.stdlib"
    TEXT = "text.decode"
    NONE = "none"


@dataclass(slots=True)
class SourceFile:
    """A downloaded file plus its provenance. ``content`` is never modified."""

    content: bytes
    source_url: str
    source_name: str = "unknown"
    source_type: str = "unknown"
    fetched_at: datetime | None = None
    declared_mime: str | None = None
    filename: str | None = None

    @property
    def size(self) -> int:
        return len(self.content)


@dataclass(slots=True)
class ValidationResult:
    is_valid: bool
    detected_mime: str | None = None
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Classification:
    doc_class: DocClass
    detected_mime: str | None = None
    confidence: float = 1.0
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DocumentMetadata:
    title: str | None = None
    author: str | None = None
    created: str | None = None
    modified: str | None = None
    page_count: int | None = None
    sheet_names: list[str] | None = None
    language: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExtractionResult:
    text: str | None
    method: str
    doc_class_final: DocClass
    confidence: float | None = None
    ocr_used: bool = False
    needs_ocr: bool = False
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NormalizedDocument:
    # provenance (preserved from the source)
    source_url: str
    source_name: str
    source_type: str
    fetched_at: datetime | None
    # identity / hashing
    sha256: str
    md5: str
    byte_size: int
    # classification & extraction
    doc_class: DocClass
    detected_mime: str | None
    declared_mime: str | None
    extraction_method: str
    extraction_confidence: float | None
    ocr_used: bool
    text: str | None
    metadata: DocumentMetadata
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProcessingOutcome:
    status: ProcessingStatus
    normalized: NormalizedDocument | None = None
    sha256: str | None = None
    error: str | None = None
    error_kind: str | None = None
    duplicate_of: str | None = None   # sha256 (or id) of an existing document
    warnings: list[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.status is ProcessingStatus.succeeded
