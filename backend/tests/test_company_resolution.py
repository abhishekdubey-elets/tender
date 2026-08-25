"""PART B — company entity resolution: normalization + false pos/neg."""
from __future__ import annotations

from app.resolution.matcher import CompanyMatcher, CompanyObservation, CompanyRecord
from app.resolution.normalize import normalize_company_name, normalize_domain
from app.resolution.service import (
    CompanyResolver,
    InMemoryCompanyProvider,
    InMemoryCompanyStore,
)

VARIANTS = [
    "M/s ABC Technologies Pvt Ltd",
    "ABC Technologies Private Limited",
    "ABC Technologies Ltd.",
]


def test_normalization_collapses_legal_variants() -> None:
    cores = {normalize_company_name(v).core for v in VARIANTS}
    assert cores == {"abc technologies"}


def test_normalize_domain() -> None:
    assert normalize_domain("https://www.ABCTech.com/about") == "abctech.com"
    assert normalize_domain(None) is None


def _rec(**kw) -> CompanyRecord:
    base = dict(ref=1, canonical_name="ABC Technologies", core="abc technologies")
    base.update(kw)
    return CompanyRecord(**base)


# --- matcher: auto merges (false negatives avoided) -------------------------
def test_legal_variant_auto_matches_on_canonical_name() -> None:
    m = CompanyMatcher()
    d = m.match(CompanyObservation("ABC Technologies Private Limited"), [_rec()])
    assert d.kind == "auto" and d.method == "canonical_name"


def test_registration_id_auto_matches() -> None:
    m = CompanyMatcher()
    rec = _rec(core="different name here", cin="U74999DL2020PTC000001")
    d = m.match(CompanyObservation("Some Other Name", cin="U74999DL2020PTC000001"), [rec])
    assert d.kind == "auto" and d.method == "cin"


def test_domain_auto_matches() -> None:
    m = CompanyMatcher()
    rec = _rec(core="xyz labs", domain="abctech.com")
    d = m.match(CompanyObservation("XYZ Labs", website="http://abctech.com"), [rec])
    assert d.kind == "auto" and d.method == "domain"


# --- matcher: FALSE POSITIVES (must NOT auto-merge) -------------------------
def test_reg_id_conflict_blocks_merge_despite_identical_name() -> None:
    m = CompanyMatcher()
    rec = _rec(cin="CIN-AAA")
    d = m.match(CompanyObservation("ABC Technologies Pvt Ltd", cin="CIN-BBB"), [rec])
    assert d.kind == "none"                     # different registration → different company


def test_similar_but_distinct_name_not_auto_merged() -> None:
    m = CompanyMatcher()
    # "ABC Technologies Solutions" is a different, more specific entity.
    d = m.match(CompanyObservation("ABC Technologies Solutions"), [_rec()])
    assert d.kind != "auto"


def test_fuzzy_typo_is_suggest_not_auto() -> None:
    m = CompanyMatcher()
    rec = _rec(core="bharat electronics")
    d = m.match(CompanyObservation("Bharath Electronics"), [rec])
    assert d.kind == "suggest"                  # flagged for review, never merged


# --- resolver: end-to-end (in-memory) ---------------------------------------
def _resolver() -> tuple[CompanyResolver, InMemoryCompanyStore]:
    store = InMemoryCompanyStore()
    return CompanyResolver(CompanyMatcher(), InMemoryCompanyProvider(store), store), store


def test_resolver_merges_variants_into_one_company() -> None:
    resolver, store = _resolver()
    results = [resolver.resolve(CompanyObservation(v)) for v in VARIANTS]
    assert results[0].created is True
    assert results[1].created is False and results[1].ref == results[0].ref
    assert results[2].ref == results[0].ref
    assert len(store.records) == 1
    # every observed variation is preserved as an alias
    assert len(store.records[results[0].ref].aliases_full) == 3


def test_resolver_does_not_merge_on_reg_id_conflict() -> None:
    resolver, store = _resolver()
    a = resolver.resolve(CompanyObservation("Acme Ltd", cin="C1"))
    b = resolver.resolve(CompanyObservation("Acme Ltd", cin="C2"))
    assert a.ref != b.ref
    assert len(store.records) == 2


def test_resolver_suggest_creates_flagged_company_not_merge() -> None:
    resolver, store = _resolver()
    a = resolver.resolve(CompanyObservation("Bharat Electronics"))
    b = resolver.resolve(CompanyObservation("Bharath Electronics"))
    assert b.created is True                     # not merged
    assert b.possible_duplicate_of == a.ref      # but flagged as a possible dup
    assert len(store.records) == 2
