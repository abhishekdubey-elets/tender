"""Claim verification against the FactBook.

Catches invented specifics — numbers, currency amounts, dates and contact
details (emails/phones) — that do not appear in any grounded fact. This is what
lets the generator reject or flag unsupported claims.
"""
from __future__ import annotations

import re

from app.brief.facts import FactBook

# Numbers, currency amounts (with cr/lakh/mn/bn), and ISO dates.
_NUM_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}"                                   # ISO date
    r"|₹?\s?\d[\d,]*(?:\.\d+)?\s?(?:cr|crore|lakh|lakhs|million|billion|bn|mn)?",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\-\s]{7,}\d)")


def _normalize_num(token: str) -> str:
    t = token.strip().lower().replace(",", "").replace("₹", "").replace(" ", "")
    t = (t.replace("crore", "cr").replace("lakhs", "lakh")
         .replace("million", "mn").replace("billion", "bn"))
    t = re.sub(r"\.0(?=cr|lakh|mn|bn|$)", "", t)          # 50.0cr -> 50cr
    return t


def _extract_num_tokens(text: str) -> set[str]:
    out = set()
    for m in _NUM_RE.findall(text):
        norm = _normalize_num(m)
        if norm:
            out.add(norm)
    return out


def allowed_num_tokens(fb: FactBook) -> set[str]:
    allowed: set[str] = set()
    for f in fb.facts:
        for s in (f.value, f.statement, f.evidence):
            if s:
                allowed.update(_extract_num_tokens(str(s)))
        # allow the bare year of any date value
        if f.value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.value):
            allowed.add(f.value[:4])
    return allowed


def allowed_contacts(fb: FactBook) -> set[str]:
    out: set[str] = set()
    for f in fb.facts:
        for s in (f.value, f.statement):
            if s:
                out.update(_EMAIL_RE.findall(s))
                out.update(p.strip() for p in _PHONE_RE.findall(s))
    return out


def find_unsupported_numbers(text: str, fb: FactBook) -> list[str]:
    allowed = allowed_num_tokens(fb)
    return sorted(t for t in _extract_num_tokens(text) if t not in allowed)


def find_unsupported_contacts(text: str, fb: FactBook) -> list[str]:
    allowed = allowed_contacts(fb)
    found = set(_EMAIL_RE.findall(text)) | {p.strip() for p in _PHONE_RE.findall(text)}
    return sorted(c for c in found if c not in allowed)
