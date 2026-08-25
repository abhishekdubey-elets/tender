"""Structured request logging + security headers. No secrets or PII are logged."""
from __future__ import annotations

import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("govintel.api")


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger("govintel")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(json.dumps(
                {"event": "request_error", "request_id": rid,
                 "method": request.method, "path": request.url.path}))
            raise
        dur_ms = round((time.perf_counter() - start) * 1000, 1)
        # Log path (never query strings, headers or bodies → no secrets/PII).
        logger.info(json.dumps(
            {"event": "request", "request_id": rid, "method": request.method,
             "path": request.url.path, "status": response.status_code, "dur_ms": dur_ms}))
        response.headers["X-Request-ID"] = rid
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        return response
