"""Read API for the dashboard.

Serves the high-priority leads board, lead detail and feedback capture. Auth is
API-key based with per-organization authorization; requests are rate-limited,
security-headed, request-id logged, and errors return safe JSON.
"""
from __future__ import annotations

from app.api.main import create_app

__all__ = ["create_app"]
