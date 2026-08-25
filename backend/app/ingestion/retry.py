"""Retry policy with exponential backoff that honours ``Retry-After``.

Sleep is injectable so tests do not wait in real time.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 3          # total attempts, including the first
    base_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 30.0
    # HTTP statuses that should be retried.
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)

    def backoff_for(self, attempt: int, retry_after: float | None = None) -> float:
        """Seconds to wait before ``attempt`` (1-indexed retry number)."""
        if retry_after is not None:
            return min(retry_after, self.max_backoff_seconds)
        delay = self.base_backoff_seconds * (2 ** (attempt - 1))
        return min(delay, self.max_backoff_seconds)


def sleep_backoff(
    policy: RetryPolicy,
    attempt: int,
    retry_after: float | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    sleep(policy.backoff_for(attempt, retry_after))
