"""Duplicate detection.

Exact duplicates are detected by sha256 content hash. :class:`DuplicateIndex`
is an in-process index used for batch processing and tests; the database path
(see :mod:`app.processing.db`) queries ``raw_documents.content_hash`` instead.
"""
from __future__ import annotations


class DuplicateIndex:
    def __init__(self) -> None:
        self._seen: dict[str, str] = {}   # sha256 -> id/reference of first seen

    def get(self, sha256: str) -> str | None:
        return self._seen.get(sha256)

    def add(self, sha256: str, ref: str) -> None:
        self._seen.setdefault(sha256, ref)

    def __contains__(self, sha256: str) -> bool:
        return sha256 in self._seen

    def __len__(self) -> int:
        return len(self._seen)
