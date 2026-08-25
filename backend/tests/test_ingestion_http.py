"""HttpClient: robots, retries, rate limiting, typed errors — all mocked."""
from __future__ import annotations

import httpx
import pytest

from app.ingestion.errors import FetchError, NotFound, RateLimited, RobotsDisallowed
from app.ingestion.rate_limiter import RateLimitConfig, RateLimiter
from app.ingestion.retry import RetryPolicy
from tests.ing_util import allow_all_robots, make_client


def test_robots_disallow_blocks_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx.Response(200, text="ok")

    client = make_client(handler)
    with pytest.raises(RobotsDisallowed):
        client.get("https://example.gov.in/private/doc")
    # A non-disallowed path still works.
    assert client.get("https://example.gov.in/public/doc").text == "ok"


def test_access_restricted_robots_denies_all() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(403, text="forbidden")
        return httpx.Response(200, text="ok")

    client = make_client(handler)
    with pytest.raises(RobotsDisallowed):
        client.get("https://locked.gov.in/anything")


def test_retry_on_429_then_success() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        robots = allow_all_robots(request)
        if robots is not None:
            return robots
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, text="slow down")
        return httpx.Response(200, text="finally")

    client = make_client(handler)
    resp = client.get("https://example.gov.in/data")
    assert resp.text == "finally"
    assert calls["n"] == 2


def test_500_exhausts_retries_raises_fetcherror() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = allow_all_robots(request)
        if robots is not None:
            return robots
        return httpx.Response(500, text="boom")

    client = make_client(handler)
    client.retry_policy = RetryPolicy(max_attempts=2, base_backoff_seconds=0)
    with pytest.raises(FetchError):
        client.get("https://example.gov.in/data")


def test_429_exhausted_raises_ratelimited() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = allow_all_robots(request)
        if robots is not None:
            return robots
        return httpx.Response(429, text="no")

    client = make_client(handler)
    client.retry_policy = RetryPolicy(max_attempts=2, base_backoff_seconds=0)
    with pytest.raises(RateLimited):
        client.get("https://example.gov.in/data")


def test_404_raises_notfound() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        robots = allow_all_robots(request)
        if robots is not None:
            return robots
        return httpx.Response(404, text="missing")

    client = make_client(handler)
    with pytest.raises(NotFound):
        client.get("https://example.gov.in/missing")


def test_rate_limiter_spaces_requests() -> None:
    """Second acquire on the same host waits out the interval."""
    slept: list[float] = []
    t = {"now": 0.0}
    limiter = RateLimiter(
        RateLimitConfig(min_interval_seconds=5.0),
        now=lambda: t["now"],
        sleep=lambda s: slept.append(s),
    )
    limiter.acquire("host")          # first: no wait
    limiter.acquire("host")          # second: must wait ~5s (no time elapsed)
    assert slept and abs(slept[0] - 5.0) < 1e-6
