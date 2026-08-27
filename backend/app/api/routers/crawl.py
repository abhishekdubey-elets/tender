"""Manual crawl trigger: POST /api/crawl.

Runs the headless Google-News → rule-extract → persist crawl and returns a summary.
Guarded by a per-app lock so a manual crawl and the scheduler never overlap. The
persisted leads fire the LISTEN/NOTIFY trigger, so the dashboard updates over the
WebSocket without the client polling.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.logging import logger
from app.api.security import Principal, rate_limit

router = APIRouter(prefix="/api", tags=["crawl"])

_LAST_CRAWL_KEY = "last_crawl_at"


async def run_crawl_guarded(app) -> dict | None:
    """Run one crawl if none is in progress; returns the report dict or None if busy."""
    lock: asyncio.Lock = app.state.crawl_lock
    if lock.locked():
        return None
    from app.crawl import run_crawl

    loop = asyncio.get_running_loop()
    async with lock:
        report = await loop.run_in_executor(None, run_crawl)

    # Record when the crawl happened — in memory, and in Mongo when available so
    # the lazy scheduler survives free-tier restarts.
    now = datetime.now(timezone.utc)
    app.state.last_crawl_at = now
    repo = app.state.repository
    if hasattr(repo, "set_meta"):
        try:
            await loop.run_in_executor(None, repo.set_meta, _LAST_CRAWL_KEY, now.isoformat())
        except Exception as exc:  # noqa: BLE001 - bookkeeping must not fail the crawl
            logger.warning('{"event": "crawl_meta_write_error", "detail": "%s"}', exc)
    return report.as_dict()


async def maybe_crawl_stale(app) -> None:
    """Lazy scheduler: run after a board load; crawls when the last crawl is older
    than crawl_interval_hours. Hosts that sleep when idle (Render free tier) never
    reach the 24h background timer, so page traffic drives the schedule instead."""
    settings = app.state.settings
    if not settings.crawl_enabled or app.state.crawl_lock.locked():
        return

    loop = asyncio.get_running_loop()
    last = getattr(app.state, "last_crawl_at", None)
    repo = app.state.repository
    if last is None and hasattr(repo, "get_meta"):
        try:
            iso = await loop.run_in_executor(None, repo.get_meta, _LAST_CRAWL_KEY)
            if iso:
                last = datetime.fromisoformat(iso)
                app.state.last_crawl_at = last
        except Exception as exc:  # noqa: BLE001 - a meta read must not break the board
            logger.warning('{"event": "crawl_meta_read_error", "detail": "%s"}', exc)
            return

    interval = timedelta(hours=max(1, settings.crawl_interval_hours))
    if last is not None and datetime.now(timezone.utc) - last < interval:
        return
    report = await run_crawl_guarded(app)
    if report is not None:
        logger.info('{"event": "lazy_crawl", "persisted": %d, "fetched": %d}',
                    report.get("persisted", 0), report.get("fetched", 0))


@router.post("/crawl")
async def trigger_crawl(request: Request, principal: Principal = Depends(rate_limit)):
    if not principal.can_write_feedback():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted to trigger a crawl")
    result = await run_crawl_guarded(request.app)
    if result is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A crawl is already running")
    return result
