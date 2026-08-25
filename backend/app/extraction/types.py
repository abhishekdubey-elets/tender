"""Result/metadata containers for an extraction run."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime

from app.extraction.schema import ExtractedEvent


class ExtractionStatus(str, enum.Enum):
    succeeded = "succeeded"
    skipped = "skipped"     # nothing to extract (e.g. empty/OCR-pending text)
    failed = "failed"       # exhausted retries without a valid, grounded result


@dataclass(slots=True)
class ExtractionRunMeta:
    provider: str
    model: str
    prompt_version: str
    requested_at: datetime
    completed_at: datetime | None = None
    attempts: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    from_cache: bool = False


@dataclass(slots=True)
class ExtractionResult:
    status: ExtractionStatus
    events: list[ExtractedEvent]
    meta: ExtractionRunMeta
    input_sha256: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def is_success(self) -> bool:
        return self.status is ExtractionStatus.succeeded
