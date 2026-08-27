"""Rule-based crawl extraction: junk company names must not become leads."""
from app.crawl.service import _valid_company, extract_rule_based


def _titles(*titles: str) -> dict:
    return {"e-Governance": [{"title": t, "source": "PTI", "date": "Wed, 26 Aug 2026"} for t in titles]}


def _companies(by_sector: dict) -> list[str]:
    return [lead["company"] for lead in extract_rule_based(by_sector)]


def test_accepts_clean_company_win():
    got = _companies(_titles(
        "TCS wins ₹500 crore e-governance contract from Ministry of Electronics & IT"))
    assert got == ["TCS"]


def test_rejects_pronoun_led_headline():
    assert _companies(_titles(
        "We win ₹50 crore order from Karnataka government")) == []


def test_rejects_editorial_and_clause_leads():
    assert _companies(_titles(
        "Why This Smallcap Gets ₹120 crore government order from railway ministry",
        "Breaking News Live Updates Today gets ₹90 crore from Ministry of Finance",
    )) == []


def test_rejects_government_body_as_company():
    assert _companies(_titles(
        "Ministry of Health awarded ₹200 crore project, government says")) == []


def test_label_prefix_is_stripped():
    got = _companies(_titles(
        "Order win: Mafatlal Industries secures ₹100 crore government contract"))
    assert got == ["Mafatlal Industries"]


def test_valid_company_shape_rules():
    assert _valid_company("Larsen & Toubro")
    assert _valid_company("RailTel Corporation of India")
    assert not _valid_company("We")
    assert not _valid_company("it")
    assert not _valid_company("")
    assert not _valid_company("x")
    assert not _valid_company("this smallcap company that just did something big today again")
    assert not _valid_company("all lowercase fragment")
