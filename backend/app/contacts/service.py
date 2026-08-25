"""ContactDiscoveryService: collect → merge → email → comply → rank."""
from __future__ import annotations

from app.contacts.compliance import CompliancePolicy, apply_compliance
from app.contacts.sources import ContactSource, EmailFinderClient
from app.contacts.types import (
    SENIORITY_RANK,
    ContactCandidate,
    ContactQuery,
    DiscoveryResult,
    normalize_name,
)


def _rank(c: ContactCandidate, target_titles: list[str]) -> float:
    score = float(SENIORITY_RANK.get(c.seniority or "unknown", 0))
    title_l = (c.title or "").lower()
    if any(t.lower() in title_l or title_l in t.lower() for t in target_titles if t):
        score += 5.0
    if c.email:
        score += 2.0
    if c.verified:
        score += 2.0
    score += (c.corroborations - 1) * 1.0
    score += c.confidence
    return round(score, 3)


def _combine(a: ContactCandidate, b: ContactCandidate) -> None:
    a.title = a.title or b.title
    a.seniority = a.seniority if a.seniority not in (None, "unknown") else b.seniority
    a.department = a.department or b.department
    a.email = a.email or b.email
    a.phone = a.phone or b.phone
    a.linkedin_url = a.linkedin_url or b.linkedin_url
    a.source_url = a.source_url or b.source_url
    a.confidence = max(a.confidence, b.confidence)
    a.verified = a.verified or b.verified
    if b.source_name and b.source_name != a.source_name:
        a.corroborations += 1
        a.source_name = f"{a.source_name}+{b.source_name}"


class ContactDiscoveryService:
    def __init__(
        self,
        sources: list[ContactSource],
        *,
        email_finder: EmailFinderClient | None = None,
        policy: CompliancePolicy | None = None,
    ) -> None:
        self._sources = sources
        self._email_finder = email_finder
        self._policy = policy or CompliancePolicy()

    def discover(self, query: ContactQuery) -> DiscoveryResult:
        candidates: list[ContactCandidate] = []
        used: list[str] = []
        warnings: list[str] = []

        for source in self._sources:
            try:
                found = source.find(query)
            except Exception as exc:  # noqa: BLE001 - isolate a failing provider
                warnings.append(f"source '{getattr(source, 'name', '?')}' failed: {exc}")
                continue
            if found:
                used.append(source.name)
                candidates.extend(found)

        # Merge duplicates across sources (same person at the company).
        merged: dict[str, ContactCandidate] = {}
        for c in candidates:
            k = normalize_name(c.name)
            if k in merged:
                _combine(merged[k], c)
            else:
                merged[k] = c

        results: list[ContactCandidate] = []
        for c in merged.values():
            # Corroboration across independent sources raises trust.
            if c.corroborations >= 2:
                c.verified = True
                c.confidence = min(0.95, c.confidence + 0.1)

            # Optional email finding/verification for contacts still missing one.
            if not c.email and self._email_finder is not None and query.domain:
                res = self._email_finder.find(name=c.name, domain=query.domain)
                if res:
                    c.email, c.verified = res.email, c.verified or res.verified
                    c.confidence = max(c.confidence, res.confidence)

            complied = apply_compliance(c, self._policy)
            if complied is None:
                continue
            complied.rank_score = _rank(complied, query.target_titles)
            results.append(complied)

        results.sort(key=lambda c: c.rank_score, reverse=True)
        return DiscoveryResult(contacts=results, sources_used=used, warnings=warnings)
