"""Contact-discovery domain types + normalization helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")

# Seniority ranking (higher = more senior) and title keywords.
SENIORITY_RANK = {"c_level": 5, "vp": 4, "director": 3, "head": 3, "manager": 2, "staff": 1, "unknown": 0}

_FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.co.in", "hotmail.com", "outlook.com",
    "rediffmail.com", "icloud.com", "proton.me", "protonmail.com",
}


def normalize_name(name: str) -> str:
    return _WS.sub(" ", _NON_ALNUM.sub("", name.lower())).strip()


def infer_seniority(title: str | None) -> str:
    t = (title or "").lower()
    if any(k in t for k in ("chief", "ceo", "cio", "ciso", "cto", "cfo", "cmo", "chro", "founder", "president")):
        return "c_level"
    if "vice president" in t or re.search(r"\bvp\b", t):
        return "vp"
    if "director" in t:
        return "director"
    if "head" in t:
        return "head"
    if "manager" in t or "lead" in t:
        return "manager"
    return "staff" if t else "unknown"


def is_free_email(email: str | None) -> bool:
    if not email or "@" not in email:
        return False
    return email.split("@", 1)[1].lower() in _FREE_EMAIL_DOMAINS


@dataclass(slots=True)
class ContactCandidate:
    name: str
    title: str | None = None
    seniority: str | None = None
    department: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    source_name: str = ""
    source_url: str | None = None
    confidence: float = 0.5
    lawful_basis: str | None = None
    do_not_contact: bool = False
    verified: bool = False
    corroborations: int = 1
    rank_score: float = 0.0

    def key(self) -> str:
        if self.email:
            return self.email.lower()
        return normalize_name(self.name) + "|" + (self.title or "").lower()


@dataclass(slots=True)
class ContactQuery:
    company_name: str
    company_id: Any | None = None
    domain: str | None = None
    target_titles: list[str] = field(default_factory=list)
    target_departments: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DiscoveryResult:
    contacts: list[ContactCandidate]
    sources_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def best(self) -> ContactCandidate | None:
        return self.contacts[0] if self.contacts else None
