"""Event matching: deterministic first, semantic only as a fallback."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Protocol, runtime_checkable

from app.dedup.fingerprint import EventFingerprint
from app.dedup.normalize import date_close, value_close


@dataclass(slots=True)
class MatchResult:
    matched: bool
    ref: Any = None
    method: str | None = None       # "identifier" | "composite" | "semantic" | None
    confidence: float = 0.0
    reason: str | None = None


NO_MATCH = MatchResult(matched=False)


@runtime_checkable
class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Dependency-free bag-of-tokens embedder.

    Deterministic and good enough for tests and as a fallback; production should
    inject a real embeddings provider (e.g. Voyage / a local sentence model).
    """

    def __init__(self, dim: int = 128) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in text.lower().split():
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        return vec


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _name_ratio(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


class EventMatcher:
    def __init__(
        self,
        embedder: Embedder | None = None,
        *,
        value_rel_tol: float = 0.02,
        date_tol_days: int = 3,
        semantic_threshold: float = 0.86,
        name_compat_threshold: float = 0.6,
    ) -> None:
        self._embedder = embedder
        self._value_rel_tol = value_rel_tol
        self._date_tol_days = date_tol_days
        self._semantic_threshold = semantic_threshold
        self._name_compat_threshold = name_compat_threshold

    # -- public -------------------------------------------------------------
    def find_match(
        self, candidate: EventFingerprint, existing: list[tuple[Any, EventFingerprint]]
    ) -> MatchResult:
        best = NO_MATCH
        for ref, fp in existing:
            result = self._compare(candidate, fp)
            if result.matched and result.confidence > best.confidence:
                best = MatchResult(True, ref, result.method, result.confidence, result.reason)
        return best

    # -- comparison ---------------------------------------------------------
    def _compare(self, cand: EventFingerprint, other: EventFingerprint) -> MatchResult:
        # 1) Deterministic: shared strong identifier.
        shared = cand.identifiers & other.identifiers
        if shared:
            return MatchResult(True, method="identifier", confidence=0.98,
                               reason=f"shared identifier {sorted(shared)}")

        # 2) Deterministic: buyer + company + (value and/or date) composite.
        composite = self._composite(cand, other)
        if composite is not None:
            return composite

        # 3) Semantic — only when deterministic signals are insufficient.
        if self._embedder is not None and cand.text and other.text:
            sim = cosine(self._embedder.embed(cand.text), self._embedder.embed(other.text))
            # Require an entity signal too, so unrelated events with generic
            # boilerplate don't collide.
            name_ok = (
                _name_ratio(cand.company, other.company) >= self._name_compat_threshold
                or _name_ratio(cand.buyer, other.buyer) >= self._name_compat_threshold
            )
            if sim >= self._semantic_threshold and name_ok:
                return MatchResult(True, method="semantic", confidence=min(0.85, sim),
                                   reason=f"semantic cosine={sim:.3f}")

        return NO_MATCH

    def _composite(self, cand: EventFingerprint, other: EventFingerprint) -> MatchResult | None:
        # Need both buyer and company present and equal.
        if not (cand.buyer and other.buyer and cand.buyer == other.buyer):
            return None
        if not (cand.company and other.company and cand.company == other.company):
            return None

        # Corroborate with value and/or date. If a field is present on BOTH it
        # must agree; at least one corroborating field must be present on both.
        value_present = cand.value is not None and other.value is not None
        date_present = cand.event_date is not None and other.event_date is not None
        if not (value_present or date_present):
            return None  # buyer+company alone is not enough → avoid false merges

        if value_present and not value_close(cand.value, other.value, rel_tol=self._value_rel_tol):
            return None
        if date_present and not date_close(cand.event_date, other.event_date, days=self._date_tol_days):
            return None

        corroborators = [c for c, present in (("value", value_present), ("date", date_present)) if present]
        return MatchResult(True, method="composite", confidence=0.9,
                           reason=f"buyer+company+{'+'.join(corroborators)}")
