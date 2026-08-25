"""Helpers for ingestion tests: build an HttpClient over a mocked transport
with no real sleeping or rate-limit waiting."""
from __future__ import annotations

from collections.abc import Callable

import httpx

from app.ingestion.http_client import HttpClient
from app.ingestion.rate_limiter import RateLimitConfig, RateLimiter

Handler = Callable[[httpx.Request], httpx.Response]

_clock = {"t": 0.0}


def _fake_now() -> float:
    return _clock["t"]


def make_client(handler: Handler, *, respect_robots: bool = True) -> HttpClient:
    transport = httpx.MockTransport(handler)
    rate_limiter = RateLimiter(
        RateLimitConfig(min_interval_seconds=0.0),
        now=_fake_now,
        sleep=lambda _s: None,
    )
    return HttpClient(
        transport=transport,
        rate_limiter=rate_limiter,
        respect_robots=respect_robots,
        sleep=lambda _s: None,
    )


def allow_all_robots(request: httpx.Request) -> httpx.Response | None:
    """Return a permissive robots response for /robots.txt, else None."""
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")
    return None
