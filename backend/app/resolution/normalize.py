"""Company-name normalization.

Produces three forms:
  * ``normalized_full`` — punctuation/case-normalized full string (alias key);
  * ``core`` — the distinctive core after dropping honorifics ("M/s") and legal
    suffixes ("Pvt Ltd", "Private Limited", "LLP", ...), used for identity
    equality;
  * ``display`` — a tidy canonical display name.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^A-Za-z0-9]+")

# Leading honorifics.
_HONORIFICS = {"m/s", "ms", "messrs", "m /s"}

# Legal-form and generic tokens dropped from the core identity key.
_LEGAL_TOKENS = {
    "private", "pvt", "limited", "ltd", "llp", "plc", "inc", "incorporated",
    "corporation", "corp", "company", "co", "and", "the", "llc", "gmbh",
    "enterprises", "enterprise",
}


@dataclass(slots=True)
class NameForms:
    display: str
    core: str
    normalized_full: str


def _strip_honorific(text: str) -> str:
    low = text.strip().lower()
    for hon in _HONORIFICS:
        if low.startswith(hon + " ") or low.startswith(hon + "."):
            return text.strip()[len(hon):].lstrip(" .")
    # also handle "m/s." with trailing dot glued
    if low.startswith("m/s"):
        return re.sub(r"^(?i)m\s*/\s*s\.?\s*", "", text.strip())
    return text.strip()


def normalize_company_name(raw: str) -> NameForms:
    without_hon = _strip_honorific(raw)
    normalized_full = _WS.sub(" ", _PUNCT.sub(" ", without_hon)).strip().lower()

    tokens = [t for t in normalized_full.split() if t and t not in _LEGAL_TOKENS]
    core = " ".join(tokens)

    # Display: title-case the honorific-stripped, whitespace-collapsed name.
    display = _WS.sub(" ", without_hon).strip()
    return NameForms(display=display, core=core, normalized_full=normalized_full)


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    v = re.sub(r"^https?://", "", v)
    v = re.sub(r"^www\.", "", v)
    v = v.split("/")[0].split("?")[0]
    return v or None
