"""Press Information Bureau (PIB) press releases via RSS.

RSS is the easiest reliable, ToS-friendly government source: it is published
expressly for machine consumption, needs no authentication or CAPTCHA, and one
request retrieves the whole feed. This adapter is a thin, declarative subclass
of the generic RSSAdapter.
"""
from __future__ import annotations

from typing import ClassVar

from app.db.enums import GovSourceType
from app.ingestion.adapters.rss_adapter import RSSAdapter
from app.ingestion.rate_limiter import RateLimitConfig
from app.ingestion.registry import register_adapter


@register_adapter
class PIBPressReleaseAdapter(RSSAdapter):
    name = "PIB Press Releases"
    source_type = GovSourceType.pib
    base_url = "https://pib.gov.in/"
    # PIB's RSS endpoint (all-India, English). Region/ministry can be varied.
    feed_url: ClassVar[str] = "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"
    # Deliberately gentle: one feed request per run, spaced politely.
    rate_limit = RateLimitConfig(min_interval_seconds=2.0)
