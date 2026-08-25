"""Per-host polite rate limiting.

A minimum interval is enforced between requests to the same host. ``crawl-delay``
from robots.txt (when larger) overrides the configured interval. The clock and
sleep function are injectable so tests never actually sleep.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(slots=True)
class RateLimitConfig:
    # Minimum seconds between requests to the same host (default: polite 1 rps).
    min_interval_seconds: float = 1.0
    # Optional absolute cap on concurrent hosts is out of scope; single-threaded
    # politeness is the goal here.


class RateLimiter:
    def __init__(
        self,
        config: RateLimitConfig | None = None,
        *,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config or RateLimitConfig()
        self._now = now
        self._sleep = sleep
        self._last_request: dict[str, float] = {}
        self._crawl_delay: dict[str, float] = {}
        self._lock = threading.Lock()

    def set_crawl_delay(self, host: str, delay_seconds: float | None) -> None:
        if delay_seconds is not None:
            self._crawl_delay[host] = delay_seconds

    def _interval_for(self, host: str) -> float:
        return max(self._config.min_interval_seconds, self._crawl_delay.get(host, 0.0))

    def acquire(self, host: str) -> None:
        """Block until it is polite to make another request to ``host``."""
        with self._lock:
            interval = self._interval_for(host)
            last = self._last_request.get(host)
            now = self._now()
            if last is not None:
                elapsed = now - last
                wait = interval - elapsed
                if wait > 0:
                    self._sleep(wait)
                    now = self._now()
            self._last_request[host] = now
