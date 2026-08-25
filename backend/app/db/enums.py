"""Controlled vocabularies, implemented as native PostgreSQL ENUM types.

Native enums give database-level validation. New values are added with a
standard migration (``ALTER TYPE ... ADD VALUE``); the trailing ``other`` /
``unknown`` members give a safe landing spot until a value is promoted to a
first-class member.
"""
from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    sales_rep = "sales_rep"
    analyst = "analyst"
    viewer = "viewer"


class GovSourceType(str, enum.Enum):
    eprocurement = "eprocurement"   # CPPP / eProcure portals
    gem = "gem"                     # Government e-Marketplace
    pib = "pib"                     # Press Information Bureau
    ministry = "ministry"           # ministry / department website
    gazette = "gazette"             # official gazette notifications
    psu = "psu"                     # public-sector-undertaking portals
    state_portal = "state_portal"   # state government portals
    rss = "rss"
    api = "api"
    other = "other"


class AccessMethod(str, enum.Enum):
    html = "html"
    api = "api"
    rss = "rss"
    playwright = "playwright"       # JS-rendered, headless-browser required
    manual = "manual"


class Jurisdiction(str, enum.Enum):
    national = "national"
    state = "state"
    district = "district"
    municipal = "municipal"
    other = "other"


class ParseStatus(str, enum.Enum):
    pending = "pending"
    parsed = "parsed"
    failed = "failed"
    skipped = "skipped"


class ExtractionStatus(str, enum.Enum):
    pending = "pending"
    extracted = "extracted"
    failed = "failed"
    skipped = "skipped"


class EventType(str, enum.Enum):
    tender = "tender"
    award = "award"
    work_order = "work_order"
    funding = "funding"
    grant = "grant"
    policy = "policy"
    approval = "approval"
    budget_allocation = "budget_allocation"
    contract = "contract"
    empanelment = "empanelment"
    mou = "mou"
    other = "other"


class EventStatus(str, enum.Enum):
    active = "active"
    superseded = "superseded"       # a later event replaces this one
    cancelled = "cancelled"
    duplicate = "duplicate"         # merged into another event


class AliasType(str, enum.Enum):
    legal_name = "legal_name"
    trade_name = "trade_name"
    abbreviation = "abbreviation"
    misspelling = "misspelling"
    as_reported = "as_reported"     # exact string as it appeared in a source
    former_name = "former_name"


class AliasSource(str, enum.Enum):
    government_event = "government_event"
    enrichment = "enrichment"
    manual = "manual"
    external = "external"


class EnrichmentProvider(str, enum.Enum):
    mca = "mca"                     # Ministry of Corporate Affairs (CIN)
    gstn = "gstn"                   # GST Network (GSTIN)
    registry = "registry"
    web = "web"
    manual = "manual"
    third_party = "third_party"
    other = "other"


class OpportunityType(str, enum.Enum):
    sponsorship = "sponsorship"
    partnership = "partnership"
    sales = "sales"
    membership = "membership"
    advertising = "advertising"
    event_participation = "event_participation"
    other = "other"


class OpportunityStatus(str, enum.Enum):
    new = "new"
    qualified = "qualified"
    contacted = "contacted"
    meeting = "meeting"
    proposal = "proposal"
    negotiation = "negotiation"
    won = "won"
    lost = "lost"
    disqualified = "disqualified"


class DetectionMethod(str, enum.Enum):
    rule = "rule"
    llm = "llm"
    manual = "manual"
    hybrid = "hybrid"


class EvidenceType(str, enum.Enum):
    event_source = "event_source"
    enrichment = "enrichment"
    contact = "contact"
    rule_match = "rule_match"
    external = "external"
    manual = "manual"


class Seniority(str, enum.Enum):
    c_level = "c_level"
    vp = "vp"
    director = "director"
    head = "head"
    manager = "manager"
    staff = "staff"
    unknown = "unknown"


class ContactSource(str, enum.Enum):
    linkedin = "linkedin"
    apollo = "apollo"
    hunter = "hunter"
    lusha = "lusha"
    website = "website"
    manual = "manual"
    referral = "referral"
    other = "other"


class BriefStatus(str, enum.Enum):
    draft = "draft"
    final = "final"
    archived = "archived"


class BriefFormat(str, enum.Enum):
    markdown = "markdown"
    plain_text = "plain_text"
    html = "html"


class OutreachChannel(str, enum.Enum):
    email = "email"
    phone = "phone"
    linkedin = "linkedin"
    whatsapp = "whatsapp"
    meeting = "meeting"
    event = "event"
    other = "other"


class OutreachDirection(str, enum.Enum):
    outbound = "outbound"
    inbound = "inbound"


class OutreachStatus(str, enum.Enum):
    planned = "planned"
    sent = "sent"
    delivered = "delivered"
    opened = "opened"
    replied = "replied"
    bounced = "bounced"
    no_response = "no_response"
    completed = "completed"


class FeedbackOutcome(str, enum.Enum):
    positive = "positive"
    negative = "negative"
    neutral = "neutral"
    converted = "converted"
    not_interested = "not_interested"
    bad_data = "bad_data"           # feeds back to extraction/resolution quality
    wrong_contact = "wrong_contact"
    duplicate = "duplicate"


class JobType(str, enum.Enum):
    crawl = "crawl"
    parse = "parse"
    extract = "extract"
    dedup = "dedup"
    resolve = "resolve"
    enrich = "enrich"
    detect_opportunity = "detect_opportunity"
    score = "score"
    generate_brief = "generate_brief"
    sync_crm = "sync_crm"
    other = "other"


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    retrying = "retrying"
    cancelled = "cancelled"


class ActorType(str, enum.Enum):
    user = "user"
    system = "system"
    job = "job"


class ScoreGrade(str, enum.Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"
