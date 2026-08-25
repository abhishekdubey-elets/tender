"""Typed ingestion errors, so callers can distinguish retryable / skippable
/ fatal conditions instead of string-matching."""
from __future__ import annotations


class IngestionError(Exception):
    """Base class for all ingestion errors."""


class RobotsDisallowed(IngestionError):
    """The URL is disallowed by the site's robots.txt — skip politely."""


class RateLimited(IngestionError):
    """Server signalled rate limiting (HTTP 429) and retries were exhausted."""


class NotFound(IngestionError):
    """Resource returned 404 — skip."""


class FetchError(IngestionError):
    """A transport/HTTP error that could not be recovered from."""

    def __init__(self, message: str, *, status: int | None = None, url: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.url = url


class ParseError(IngestionError):
    """A document could not be parsed. The raw document is still preserved."""
