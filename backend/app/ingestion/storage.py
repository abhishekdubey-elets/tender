"""Raw-response storage and the sink abstraction.

A *sink* persists fetched documents (and their optional parse result). Sinks
enforce idempotency via ``exists(source_name, content_hash)``. Two sinks ship:
:class:`InMemorySink` (tests) and, in :mod:`app.ingestion.db_sink`, a
SQLAlchemy-backed sink that writes ``raw_documents`` rows.

Binary payloads (PDF/XLSX) are written to a :class:`FilesystemRawStorage` so the
authoritative bytes are preserved outside the database.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.ingestion.types import FetchedDocument, ParsedContent

_TEXT_KINDS_EXT = {
    "application/json": ".json",
    "text/html": ".html",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}


@runtime_checkable
class RawDocumentSink(Protocol):
    def exists(self, source_name: str, content_hash: str) -> bool: ...

    def store(self, document: FetchedDocument, parsed: ParsedContent | None) -> str: ...


class FilesystemRawStorage:
    """Stores raw bytes on disk under ``root/<source>/<hash><ext>``."""

    def __init__(self, root: str) -> None:
        self.root = root

    def save(self, document: FetchedDocument) -> str:
        ext = _TEXT_KINDS_EXT.get(document.metadata.content_type or "", ".bin")
        safe_source = "".join(c if c.isalnum() or c in "-_" else "_" for c in document.source_name)
        directory = os.path.join(self.root, safe_source)
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{document.content_hash}{ext}")
        if not os.path.exists(path):
            with open(path, "wb") as fh:
                fh.write(document.content)
        return path


@dataclass
class StoredRecord:
    document: FetchedDocument
    parsed: ParsedContent | None


@dataclass
class InMemorySink:
    """In-memory sink for tests. Idempotent by (source_name, content_hash)."""

    records: dict[tuple[str, str], StoredRecord] = field(default_factory=dict)

    def exists(self, source_name: str, content_hash: str) -> bool:
        return (source_name, content_hash) in self.records

    def store(self, document: FetchedDocument, parsed: ParsedContent | None) -> str:
        key = (document.source_name, document.content_hash)
        self.records[key] = StoredRecord(document=document, parsed=parsed)
        return document.content_hash

    def __len__(self) -> int:
        return len(self.records)
