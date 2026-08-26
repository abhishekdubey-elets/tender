"""robots.txt compliance.

We always consult robots.txt before fetching and honour ``Disallow`` rules and
``Crawl-delay``. Access-restricted robots (401/403) are treated as a full
disallow — we never try to work around access controls.

The robots file is fetched through an injected ``fetcher`` (the same transport
the client uses), so tests can supply canned robots files.
"""
from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

# fetcher(url) -> (status_code, text) or None on transport failure.
Fetcher = Callable[[str], "tuple[int, str] | None"]


class RobotsChecker:
    def __init__(
        self,
        user_agent: str,
        fetcher: Fetcher,
        *,
        allow_on_error: bool = True,
        forbidden_is_disallow: bool = True,
    ) -> None:
        self._user_agent = user_agent
        self._fetcher = fetcher
        self._allow_on_error = allow_on_error
        # By default a 401/403 on robots.txt is treated as a site-wide disallow
        # (we never work around access controls). Some public, machine-facing
        # sources (e.g. government RSS behind a bot-WAF) publish no robots.txt and
        # merely 403 the robots request itself; for those a caller may opt to
        # treat "robots unavailable" as allowed, per RFC 9309 §2.3.1.3.
        self._forbidden_is_disallow = forbidden_is_disallow
        self._cache: dict[str, RobotFileParser | None] = {}
        # host -> explicit allow/deny-all decision when there are no parseable
        # rules (e.g. 401/403 → deny all, 404 → allow all).
        self._blanket: dict[str, bool] = {}

    @staticmethod
    def _host_key(url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    def _load(self, url: str) -> None:
        host = self._host_key(url)
        if host in self._cache or host in self._blanket:
            return
        robots_url = f"{host}/robots.txt"
        result = self._fetcher(robots_url)

        if result is None:
            # Transport failure: allow (transient) unless configured strict.
            self._blanket[host] = self._allow_on_error
            return

        status, text = result
        if status in (401, 403):
            # access restricted → full disallow, unless the caller opts to treat
            # an unavailable robots.txt as unrestricted for this source.
            self._blanket[host] = not self._forbidden_is_disallow
            return
        if 400 <= status < 500:
            self._blanket[host] = True         # e.g. 404 → no restrictions
            return
        if status >= 500:
            self._blanket[host] = self._allow_on_error
            return

        rfp = RobotFileParser()
        rfp.parse(text.splitlines())
        self._cache[host] = rfp

    def can_fetch(self, url: str) -> bool:
        self._load(url)
        host = self._host_key(url)
        if host in self._blanket:
            return self._blanket[host]
        rfp = self._cache.get(host)
        if rfp is None:
            return self._allow_on_error
        return rfp.can_fetch(self._user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        self._load(url)
        host = self._host_key(url)
        rfp = self._cache.get(host)
        if rfp is None:
            return None
        delay = rfp.crawl_delay(self._user_agent)
        return float(delay) if delay is not None else None
