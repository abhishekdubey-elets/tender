"""Contact discovery: dedup, ranking, compliance, email finding."""
from __future__ import annotations

from app.contacts import CompliancePolicy, ContactDiscoveryService, ContactQuery
from app.contacts.integration import to_contact_info
from app.contacts.sources import DirectorySource, EmailResult, ProviderSource


class FakePeople:
    def __init__(self, rows):
        self._rows = rows

    def search(self, *, company, domain, titles):
        return list(self._rows)


class FakeEmailFinder:
    def __init__(self, mapping):
        self._mapping = mapping

    def find(self, *, name, domain):
        hit = self._mapping.get(name)
        return EmailResult(email=hit, verified=True, confidence=0.8) if hit else None


QUERY = ContactQuery(company_name="Acme Defence Ltd", domain="acmedefence.com",
                     target_titles=["CISO", "CIO"], target_departments=["IT Security"])


def test_dedup_and_ranking_across_sources() -> None:
    directory = DirectorySource(FakePeople([
        {"name": "Priya Rao", "title": "Chief Information Security Officer",
         "linkedin_url": "https://linkedin/priya"},
    ]))
    provider = ProviderSource(FakePeople([
        {"name": "Priya Rao", "title": "CISO", "email": "priya@acmedefence.com"},
        {"name": "Raj Mehta", "title": "IT Manager", "email": "raj@acmedefence.com"},
    ]))
    result = ContactDiscoveryService([directory, provider]).discover(QUERY)

    top = result.best()
    assert top.name == "Priya Rao"                 # role-matched c-level ranks first
    assert top.email == "priya@acmedefence.com"    # merged from provider
    assert top.corroborations == 2 and top.verified is True
    assert top.seniority == "c_level"
    # the manager ranks below
    assert result.contacts[1].name == "Raj Mehta"
    assert set(result.sources_used) == {"directory", "provider"}


def test_personal_email_is_suppressed() -> None:
    provider = ProviderSource(FakePeople([
        {"name": "Sam Roy", "title": "Director", "email": "sam@gmail.com"},
    ]))
    contact = ContactDiscoveryService([provider]).discover(QUERY).best()
    assert contact.email is None                    # personal email dropped
    assert "personal email suppressed" in contact.lawful_basis
    assert contact.name == "Sam Roy"                # contact retained via profile


def test_do_not_contact_is_honoured() -> None:
    provider = ProviderSource(FakePeople([
        {"name": "Priya Rao", "title": "CISO", "email": "priya@acmedefence.com"},
        {"name": "Raj Mehta", "title": "IT Manager", "email": "raj@acmedefence.com"},
    ]))
    policy = CompliancePolicy(do_not_contact_emails={"raj@acmedefence.com"})
    result = ContactDiscoveryService([provider], policy=policy).discover(QUERY)
    assert all(c.name != "Raj Mehta" for c in result.contacts)


def test_lawful_basis_is_recorded() -> None:
    provider = ProviderSource(FakePeople([{"name": "Priya Rao", "title": "CISO"}]))
    contact = ContactDiscoveryService([provider]).discover(QUERY).best()
    assert contact.lawful_basis and "business" in contact.lawful_basis.lower()


def test_email_finder_fills_missing_email() -> None:
    directory = DirectorySource(FakePeople([
        {"name": "Priya Rao", "title": "CISO", "linkedin_url": "https://linkedin/priya"},
    ]))
    finder = FakeEmailFinder({"Priya Rao": "priya@acmedefence.com"})
    contact = ContactDiscoveryService([directory], email_finder=finder).discover(QUERY).best()
    assert contact.email == "priya@acmedefence.com"
    assert contact.verified is True


def test_failing_source_isolated() -> None:
    class Boom:
        name = "boom"

        def find(self, query):
            raise RuntimeError("api down")

    good = ProviderSource(FakePeople([{"name": "Priya Rao", "title": "CISO"}]))
    result = ContactDiscoveryService([Boom(), good]).discover(QUERY)
    assert result.best().name == "Priya Rao"
    assert any("boom" in w for w in result.warnings)


def test_to_contact_info_bridge() -> None:
    provider = ProviderSource(FakePeople([
        {"name": "Priya Rao", "title": "CISO", "email": "priya@acmedefence.com"},
    ]))
    provider2 = DirectorySource(FakePeople([{"name": "Priya Rao", "title": "CISO"}]))
    top = ContactDiscoveryService([provider, provider2]).discover(QUERY).best()
    info = to_contact_info(top)
    assert info.name == "Priya Rao" and info.verified is True and info.email == "priya@acmedefence.com"
