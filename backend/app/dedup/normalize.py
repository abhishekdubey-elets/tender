"""Normalization helpers for deterministic matching."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")
_WS = re.compile(r"\s+")


def normalize_identifier(value: str | None) -> str | None:
    """Uppercase, strip every non-alphanumeric character.

    'GEM/2026/B/12345' and 'gem 2026 b 12345' → 'GEM2026B12345'.
    """
    if not value:
        return None
    cleaned = _NON_ALNUM.sub("", value).upper()
    return cleaned or None


def normalize_name(value: str | None) -> str | None:
    """Lowercase, collapse whitespace, drop punctuation — for buyer/company
    equality comparisons."""
    if not value:
        return None
    cleaned = _NON_ALNUM.sub(" ", value).lower()
    cleaned = _WS.sub(" ", cleaned).strip()
    return cleaned or None


def value_close(a: Decimal | float | None, b: Decimal | float | None, *, rel_tol: float = 0.02) -> bool:
    if a is None or b is None:
        return False
    da, db = Decimal(str(a)), Decimal(str(b))
    if da == db:
        return True
    if da == 0 or db == 0:
        return False
    diff = abs(da - db)
    return diff <= (max(abs(da), abs(db)) * Decimal(str(rel_tol)))


def date_close(a: date | None, b: date | None, *, days: int = 3) -> bool:
    if a is None or b is None:
        return False
    return abs((a - b).days) <= days
