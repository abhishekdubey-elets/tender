"""Typed processing errors."""
from __future__ import annotations


class ProcessingError(Exception):
    """Base class."""

    kind = "processing_error"


class InvalidFileError(ProcessingError):
    """File failed validation (empty, too large, corrupt, unrecognised)."""

    kind = "invalid_file"


class UnsupportedDocumentError(ProcessingError):
    """Recognised but unsupported format (e.g. legacy binary .doc/.xls)."""

    kind = "unsupported"


class ExtractionFailure(ProcessingError):
    """Extraction was attempted but failed (corrupt payload, bad encoding)."""

    kind = "extraction_failed"
