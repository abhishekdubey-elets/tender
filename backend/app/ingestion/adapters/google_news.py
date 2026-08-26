"""Google News RSS search adapter — a discovery feed, not an authority.

Google News exposes a per-query RSS endpoint (no key, machine-readable) that is a
fast way to *discover* candidate signals ("Company X wins Rs Y crore government
order"). It is a **secondary** source: news, not the official document — every
lead it surfaces should be cross-checked against a government source, and it is
weighted low in scoring (see app/scoring/source_authority.py).

Unlike singleton sources (PIB, data.gov.in) this adapter is parameterised by a
search query, so it is *not* auto-registered; construct it explicitly per query.
"""
from __future__ import annotations

from typing import ClassVar
from urllib.parse import quote_plus

from app.db.enums import GovSourceType
from app.ingestion.adapters.rss_adapter import RSSAdapter
from app.ingestion.rate_limiter import RateLimitConfig


class GoogleNewsRSSAdapter(RSSAdapter):
    name = "Google News"
    source_type = GovSourceType.rss
    base_url = "https://news.google.com/"
    # News aggregator: low authority; leads need cross-checking against a gov source.
    source_authority: ClassVar[float] = 0.65
    rate_limit = RateLimitConfig(min_interval_seconds=2.0)

    def __init__(self, query: str, *, hl: str = "en-IN", gl: str = "IN", ceid: str = "IN:en") -> None:
        self.query = query
        # Instance attribute shadows RSSAdapter's feed_url ClassVar.
        self.feed_url = (
            f"https://news.google.com/rss/search?q={quote_plus(query)}"
            f"&hl={hl}&gl={gl}&ceid={ceid}"
        )
