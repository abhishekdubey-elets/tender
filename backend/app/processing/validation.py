"""File validation. Invalid files are flagged with a reason — never discarded
silently; the caller still preserves the original bytes."""
from __future__ import annotations

from app.processing.sniff import sniff
from app.processing.types import DocClass, SourceFile, ValidationResult

DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


def validate(source: SourceFile, *, max_bytes: int = DEFAULT_MAX_BYTES) -> ValidationResult:
    if source.size == 0:
        return ValidationResult(is_valid=False, reason="empty_file")
    if source.size > max_bytes:
        return ValidationResult(
            is_valid=False,
            reason=f"too_large ({source.size} > {max_bytes} bytes)",
        )

    result = sniff(source.content, declared_mime=source.declared_mime, filename=source.filename)
    warnings: list[str] = []

    # A mismatch between declared and detected type is a warning, not a failure —
    # we trust the bytes, but record the discrepancy.
    if source.declared_mime and result.mime and source.declared_mime.split(";")[0].strip() != result.mime:
        warnings.append(
            f"declared_mime '{source.declared_mime}' != detected '{result.mime}'"
        )

    if result.doc_class is DocClass.unknown:
        return ValidationResult(
            is_valid=False,
            detected_mime=result.mime,
            reason="unrecognized_format",
            warnings=warnings,
        )

    return ValidationResult(is_valid=True, detected_mime=result.mime, warnings=warnings)
