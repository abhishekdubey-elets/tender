"""Evidence grounding.

An evidence snippet is *grounded* if it appears (verbatim, up to whitespace and
case normalisation) in the source document. Ungrounded snippets indicate the
model paraphrased or invented support — we either force a retry or strip them and
lower confidence, so invented claims never pass silently.
"""
from __future__ import annotations

import re

from app.extraction.schema import EventExtractionEnvelope

_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def is_grounded(snippet: str, source_text: str) -> bool:
    snip = _normalize(snippet)
    if not snip:
        return False
    return snip in _normalize(source_text)


def find_ungrounded(envelope: EventExtractionEnvelope, source_text: str) -> list[tuple[int, str]]:
    """Return (event_index, snippet) for every ungrounded evidence snippet."""
    norm_source = _normalize(source_text)
    ungrounded: list[tuple[int, str]] = []
    for i, event in enumerate(envelope.events):
        for ev in event.evidence:
            if _normalize(ev.snippet) not in norm_source:
                ungrounded.append((i, ev.snippet))
    return ungrounded


def strip_ungrounded(envelope: EventExtractionEnvelope, source_text: str) -> int:
    """Remove ungrounded evidence in place. Returns how many were removed."""
    norm_source = _normalize(source_text)
    removed = 0
    for event in envelope.events:
        kept = []
        for ev in event.evidence:
            if _normalize(ev.snippet) in norm_source:
                kept.append(ev)
            else:
                removed += 1
        event.evidence = kept
    return removed
