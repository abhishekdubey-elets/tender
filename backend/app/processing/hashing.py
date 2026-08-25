"""Document hashing and exact-duplicate keys.

sha256 is the canonical content hash used for duplicate detection and
idempotency; md5 is kept as a cheaper secondary key some external systems use.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(slots=True)
class Hashes:
    sha256: str
    md5: str
    byte_size: int


def compute_hashes(content: bytes) -> Hashes:
    return Hashes(
        sha256=hashlib.sha256(content).hexdigest(),
        md5=hashlib.md5(content).hexdigest(),
        byte_size=len(content),
    )
