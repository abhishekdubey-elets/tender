"""CompanyResolver: resolve an observed company to a canonical entity.

Storage is behind ``CompanyProvider`` / ``CompanyStore`` protocols so the logic
is testable without a database. On a fuzzy-only "suggest", a NEW company is
created (never an automatic merge) but flagged with ``possible_duplicate_of`` for
human review — respecting "never merge two companies solely on name similarity".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.resolution.matcher import CompanyMatcher, CompanyObservation, CompanyRecord, MatchDecision


@dataclass(slots=True)
class ResolutionResult:
    ref: Any
    created: bool
    decision: MatchDecision
    confidence: float
    possible_duplicate_of: Any = None


@runtime_checkable
class CompanyProvider(Protocol):
    def candidates(self, obs: CompanyObservation) -> list[CompanyRecord]: ...


@runtime_checkable
class CompanyStore(Protocol):
    def create_company(
        self, obs: CompanyObservation, *, possible_duplicate_of: Any = None, evidence: Any = None
    ) -> Any: ...

    def add_alias(self, ref: Any, obs: CompanyObservation) -> None: ...

    def merge_attrs(self, ref: Any, obs: CompanyObservation) -> None: ...


class CompanyResolver:
    def __init__(self, matcher: CompanyMatcher, provider: CompanyProvider, store: CompanyStore) -> None:
        self._matcher = matcher
        self._provider = provider
        self._store = store

    def resolve(self, obs: CompanyObservation, *, evidence: Any = None) -> ResolutionResult:
        existing = self._provider.candidates(obs)
        decision = self._matcher.match(obs, existing)

        if decision.kind == "auto":
            self._store.add_alias(decision.ref, obs)   # record the observed variation
            self._store.merge_attrs(decision.ref, obs)  # fill in any missing ids/attrs
            return ResolutionResult(decision.ref, False, decision, decision.confidence)

        if decision.kind == "suggest":
            ref = self._store.create_company(
                obs, possible_duplicate_of=decision.ref, evidence=evidence
            )
            return ResolutionResult(ref, True, decision, decision.confidence, decision.ref)

        ref = self._store.create_company(obs, evidence=evidence)
        return ResolutionResult(ref, True, decision, 1.0)


# --------------------------------------------------------------------------- #
# In-memory implementations (tests)
# --------------------------------------------------------------------------- #
class InMemoryCompanyStore:
    def __init__(self) -> None:
        self.records: dict[int, CompanyRecord] = {}
        self.evidence: dict[int, list[Any]] = {}
        self.possible_duplicates: dict[int, Any] = {}
        self._next = 1

    def create_company(
        self, obs: CompanyObservation, *, possible_duplicate_of: Any = None, evidence: Any = None
    ) -> int:
        ref = self._next
        self._next += 1
        forms = obs.forms
        self.records[ref] = CompanyRecord(
            ref=ref,
            canonical_name=forms.display,
            core=forms.core,
            aliases_full={forms.normalized_full},
            cin=obs.cin, gstin=obs.gstin, pan=obs.pan, domain=obs.domain,
            state=obs.state, city=obs.city,
        )
        if evidence is not None:
            self.evidence.setdefault(ref, []).append(evidence)
        if possible_duplicate_of is not None:
            self.possible_duplicates[ref] = possible_duplicate_of
        return ref

    def add_alias(self, ref: int, obs: CompanyObservation) -> None:
        self.records[ref].aliases_full.add(obs.forms.normalized_full)

    def merge_attrs(self, ref: int, obs: CompanyObservation) -> None:
        rec = self.records[ref]
        rec.cin = rec.cin or obs.cin
        rec.gstin = rec.gstin or obs.gstin
        rec.pan = rec.pan or obs.pan
        rec.domain = rec.domain or obs.domain
        rec.state = rec.state or obs.state
        rec.city = rec.city or obs.city


class InMemoryCompanyProvider:
    def __init__(self, store: InMemoryCompanyStore) -> None:
        self._store = store

    def candidates(self, obs: CompanyObservation) -> list[CompanyRecord]:
        return list(self._store.records.values())
