"""Authentication, authorization principal, and rate limiting."""
from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status


@dataclass(slots=True)
class Principal:
    api_key_id: str          # a non-secret identifier (never the raw key)
    organization_id: str
    role: str

    def can_write_feedback(self) -> bool:
        return self.role in {"admin", "manager", "sales_rep", "analyst"}


def _resolve(api_key: str, api_keys: dict[str, str]) -> Principal | None:
    # Constant-time comparison against each configured key.
    for known, spec in api_keys.items():
        if hmac.compare_digest(api_key, known):
            org, _, role = spec.partition(":")
            return Principal(api_key_id=known[:6] + "…", organization_id=org, role=role or "viewer")
    return None


def get_principal(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Principal:
    api_keys: dict[str, str] = request.app.state.settings.api_keys
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key required",
                            headers={"WWW-Authenticate": "ApiKey"})
    principal = _resolve(x_api_key, api_keys)
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key",
                            headers={"WWW-Authenticate": "ApiKey"})
    return principal


class RateLimiter:
    """Fixed-window-ish sliding limiter: N requests per 60s per key."""

    def __init__(self, per_minute: int, *, now=time.monotonic) -> None:
        self._limit = per_minute
        self._now = now
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, int]:
        now = self._now()
        window = self._hits[key]
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= self._limit:
            retry_after = max(1, int(60 - (now - window[0])))
            return False, retry_after
        window.append(now)
        return True, 0


def rate_limit(request: Request, principal: Principal = Depends(get_principal)) -> Principal:
    limiter: RateLimiter = request.app.state.rate_limiter
    key = f"{principal.api_key_id}:{request.client.host if request.client else '?'}"
    allowed, retry_after = limiter.check(key)
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded",
                            headers={"Retry-After": str(retry_after)})
    return principal
