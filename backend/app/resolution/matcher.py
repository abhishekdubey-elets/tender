"""Company matching. Decides auto-merge / suggest / no-match with evidence.

Guiding rules:
  * a registration-id **conflict** (both have a CIN/GSTIN and they differ) blocks
    any merge — they are different companies;
  * matching registration id or domain → auto-merge (strong identity);
  * exact canonical-name equality → auto-merge (same name, different legal form),
    strengthened by a location match;
  * mere fuzzy name similarity → **suggest only**, never an automatic merge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from app.resolution.normalize import NameForms, normalize_company_name, normalize_domain


@dataclass(slots=True)
class CompanyObservation:
    raw_name: str
    cin: str | None = None
    gstin: str | None = None
    pan: str | None = None
    website: str | None = None
    state: str | None = None
    city: str | None = None

    @property
    def forms(self) -> NameForms:
        return normalize_company_name(self.raw_name)

    @property
    def domain(self) -> str | None:
        return normalize_domain(self.website)


@dataclass(slots=True)
class CompanyRecord:
    ref: Any
    canonical_name: str
    core: str
    aliases_full: set[str] = field(default_factory=set)
    cin: str | None = None
    gstin: str | None = None
    pan: str | None = None
    domain: str | None = None
    state: str | None = None
    city: str | None = None


@dataclass(slots=True)
class MatchDecision:
    kind: str                       # "auto" | "suggest" | "none"
    ref: Any = None
    method: str | None = None
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)


NO_DECISION = MatchDecision(kind="none")

_FUZZY_SUGGEST_THRESHOLD = 0.9


def _loc_match(obs: CompanyObservation, rec: CompanyRecord) -> bool:
    def norm(x: str | None) -> str | None:
        return x.strip().lower() if x else None
    o_state, o_city = norm(obs.state), norm(obs.city)
    r_state, r_city = norm(rec.state), norm(rec.city)
    if o_city and r_city and o_city == r_city:
        return True
    return bool(o_state and r_state and o_state == r_state)


def _reg_conflict(obs: CompanyObservation, rec: CompanyRecord) -> bool:
    for a, b in ((obs.cin, rec.cin), (obs.gstin, rec.gstin), (obs.pan, rec.pan)):
        if a and b and a.strip().upper() != b.strip().upper():
            return True
    return False


class CompanyMatcher:
    def match(
        self, obs: CompanyObservation, existing: list[CompanyRecord]
    ) -> MatchDecision:
        best_auto = NO_DECISION
        best_suggest = NO_DECISION
        for rec in existing:
            decision = self._compare(obs, rec)
            if decision.kind == "auto" and decision.confidence > best_auto.confidence:
                best_auto = decision
            elif decision.kind == "suggest" and decision.confidence > best_suggest.confidence:
                best_suggest = decision
        if best_auto.kind == "auto":
            return best_auto
        return best_suggest

    def _compare(self, obs: CompanyObservation, rec: CompanyRecord) -> MatchDecision:
        # Hard block: conflicting registration identifiers → different companies.
        if _reg_conflict(obs, rec):
            return MatchDecision("none", rec.ref, "reg_id_conflict", 0.0,
                                 ["registration id conflict"])

        forms = obs.forms
        obs_domain = obs.domain

        # Strong identity signals → auto.
        if obs.cin and rec.cin and obs.cin.strip().upper() == rec.cin.strip().upper():
            return MatchDecision("auto", rec.ref, "cin", 0.99, [f"CIN={rec.cin}"])
        if obs.gstin and rec.gstin and obs.gstin.strip().upper() == rec.gstin.strip().upper():
            return MatchDecision("auto", rec.ref, "gstin", 0.98, [f"GSTIN={rec.gstin}"])
        if obs.pan and rec.pan and obs.pan.strip().upper() == rec.pan.strip().upper():
            return MatchDecision("auto", rec.ref, "pan", 0.95, [f"PAN={rec.pan}"])
        if obs_domain and rec.domain and obs_domain == rec.domain:
            return MatchDecision("auto", rec.ref, "domain", 0.9, [f"domain={rec.domain}"])

        # Exact canonical-name identity (same name, different legal form / alias).
        name_equal = forms.core and (forms.core == rec.core or forms.normalized_full in rec.aliases_full)
        if name_equal:
            if _loc_match(obs, rec):
                return MatchDecision("auto", rec.ref, "name+location", 0.92,
                                     [f"core='{forms.core}'", "location match"])
            return MatchDecision("auto", rec.ref, "canonical_name", 0.85, [f"core='{forms.core}'"])

        # Fuzzy similarity → suggest only (never an automatic merge on similarity).
        ratio = SequenceMatcher(None, forms.core, rec.core).ratio() if forms.core and rec.core else 0.0
        if ratio >= _FUZZY_SUGGEST_THRESHOLD:
            return MatchDecision("suggest", rec.ref, "fuzzy_name", round(ratio, 3),
                                 [f"name similarity={ratio:.2f} (needs review)"])

        return NO_DECISION
