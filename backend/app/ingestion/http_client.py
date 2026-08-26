"""Polite HTTP client shared by all adapters.

Responsibilities (all cross-cutting, so adapters never re-implement them):
  * robots.txt compliance (skip disallowed URLs)
  * per-host rate limiting (honours robots Crawl-delay)
  * retries with backoff, honouring ``Retry-After`` on 429/503
  * typed error handling (NotFound / RateLimited / RobotsDisallowed / FetchError)

Transport is injectable (``httpx.MockTransport`` in tests), so the full client —
including retry/robots/rate-limit behaviour — is testable without any network.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from app.ingestion.errors import FetchError, NotFound, RateLimited, RobotsDisallowed
from app.ingestion.rate_limiter import RateLimiter
from app.ingestion.retry import RetryPolicy
from app.ingestion.robots import RobotsChecker

DEFAULT_USER_AGENT = (
    "GovIntelBot/0.1 (+https://elets.in; contact: dme@elets.in) "
    "polite-government-open-data-collector"
)


@dataclass(slots=True)
class HttpResponse:
    url: str
    status: int
    content: bytes
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


def _host_of(url: str) -> str:
    return urlsplit(url).netloc


def _parse_retry_after(headers: dict[str, str]) -> float | None:
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(int(value))
    except (TypeError, ValueError):
        return None  # HTTP-date form not supported; fall back to backoff


class HttpClient:
    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: httpx.BaseTransport | None = None,
        rate_limiter: RateLimiter | None = None,
        retry_policy: RetryPolicy | None = None,
        respect_robots: bool = True,
        robots_forbidden_is_disallow: bool = True,
        timeout: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.user_agent = user_agent
        self.retry_policy = retry_policy or RetryPolicy()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.respect_robots = respect_robots
        self._sleep = sleep
        self._client = httpx.Client(
            transport=transport,
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
        )
        self.robots = RobotsChecker(
            user_agent, self._robots_fetch,
            forbidden_is_disallow=robots_forbidden_is_disallow,
        )

    # -- context management -------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- robots fetch (no robots-check / no retry, to avoid recursion) -------
    def _robots_fetch(self, url: str) -> tuple[int, str] | None:
        try:
            resp = self._client.get(url)
        except httpx.HTTPError:
            return None
        return resp.status_code, resp.text

    # -- single request -----------------------------------------------------
    def _perform(self, url: str) -> httpx.Response:
        return self._client.get(url)

    def _request_with_retry(self, url: str) -> HttpResponse:
        host = _host_of(url)
        policy = self.retry_policy
        last_error: Exception | None = None

        for attempt in range(1, policy.max_attempts + 1):
            self.rate_limiter.acquire(host)
            try:
                resp = self._perform(url)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < policy.max_attempts:
                    self._sleep(policy.backoff_for(attempt))
                    continue
                raise FetchError(f"transport error: {exc}", url=url) from exc

            headers = {k.lower(): v for k, v in resp.headers.items()}
            status = resp.status_code

            if status == 404:
                raise NotFound(url)
            if status in policy.retry_statuses:
                if attempt < policy.max_attempts:
                    self._sleep(policy.backoff_for(attempt, _parse_retry_after(headers)))
                    continue
                if status == 429:
                    raise RateLimited(url)
                raise FetchError(f"server error {status}", status=status, url=url)
            if status >= 400:
                raise FetchError(f"http error {status}", status=status, url=url)

            return HttpResponse(url=str(resp.url), status=status, content=resp.content, headers=headers)

        # Only reached if every attempt raised a transport error.
        raise FetchError(f"exhausted retries: {last_error}", url=url)

    # -- public API ---------------------------------------------------------
    def get(self, url: str) -> HttpResponse:
        if self.respect_robots:
            if not self.robots.can_fetch(url):
                raise RobotsDisallowed(url)
            self.rate_limiter.set_crawl_delay(_host_of(url), self.robots.crawl_delay(url))
        return self._request_with_retry(url)
