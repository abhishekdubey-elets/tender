"""Contact source adapters over injected provider clients.

These call provider *APIs* (people-search, email-finder). They never scrape
behind logins or solve CAPTCHAs. Clients are injected, so tests use fakes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.contacts.types import ContactCandidate, ContactQuery, infer_seniority


@runtime_checkable
class PeopleSearchClient(Protocol):
    # Returns raw people dicts: {name, title, department?, email?, phone?, linkedin_url?}
    def search(self, *, company: str, domain: str | None, titles: list[str]) -> list[dict]: ...


@dataclass(slots=True)
class EmailResult:
    email: str
    verified: bool = False
    confidence: float = 0.6


@runtime_checkable
class EmailFinderClient(Protocol):
    def find(self, *, name: str, domain: str | None) -> EmailResult | None: ...


@runtime_checkable
class ContactSource(Protocol):
    name: str

    def find(self, query: ContactQuery) -> list[ContactCandidate]: ...


class _ApiPeopleSource:
    """Shared implementation over a people-search client."""

    def __init__(self, name: str, client: PeopleSearchClient, *, base_confidence: float,
                 lawful_basis: str, verified_default: bool = False) -> None:
        self.name = name
        self._client = client
        self._base = base_confidence
        self._lawful = lawful_basis
        self._verified_default = verified_default

    def find(self, query: ContactQuery) -> list[ContactCandidate]:
        rows = self._client.search(company=query.company_name, domain=query.domain,
                                   titles=query.target_titles)
        out: list[ContactCandidate] = []
        for r in rows:
            name = r.get("name")
            if not name:
                continue
            out.append(ContactCandidate(
                name=name, title=r.get("title"), seniority=infer_seniority(r.get("title")),
                department=r.get("department"), email=r.get("email"), phone=r.get("phone"),
                linkedin_url=r.get("linkedin_url"),
                source_name=self.name, source_url=r.get("linkedin_url") or r.get("source_url"),
                confidence=self._base, lawful_basis=self._lawful,
                verified=self._verified_default and bool(r.get("email")),
            ))
        return out


class DirectorySource(_ApiPeopleSource):
    """Public professional-directory people search (LinkedIn-style API)."""

    def __init__(self, client: PeopleSearchClient) -> None:
        super().__init__(
            "directory", client, base_confidence=0.6,
            lawful_basis="legitimate interest: public professional profile (business context)",
        )


class ProviderSource(_ApiPeopleSource):
    """B2B contact-data provider (Apollo/Lusha-style API), often with emails."""

    def __init__(self, client: PeopleSearchClient) -> None:
        super().__init__(
            "provider", client, base_confidence=0.7,
            lawful_basis="legitimate interest: B2B contact database (business context)",
            verified_default=False,
        )
