"""Manual crawl trigger: POST /api/crawl.

Runs the headless Google-News → rule-extract → persist crawl and returns a summary.
Guarded by a per-app lock so a manual crawl and the scheduler never overlap. The
persisted leads fire the LISTEN/NOTIFY trigger, so the dashboard updates over the
WebSocket without the client polling.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.security import Principal, rate_limit

router = APIRouter(prefix="/api", tags=["crawl"])


async def run_crawl_guarded(app) -> dict | None:
    """Run one crawl if none is in progress; returns the report dict or None if busy."""
    lock: asyncio.Lock = app.state.crawl_lock
    if lock.locked():
        return None
    from app.crawl import run_crawl

    async with lock:
        report = await asyncio.get_running_loop().run_in_executor(None, run_crawl)
    return report.as_dict()


@router.post("/crawl")
async def trigger_crawl(request: Request, principal: Principal = Depends(rate_limit)):
    if not principal.can_write_feedback():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted to trigger a crawl")
    result = await run_crawl_guarded(request.app)
    if result is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A crawl is already running")
    return result
