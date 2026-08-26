"""FastAPI app factory."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.logging import (
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    configure_logging,
    logger,
)
from app.api.repository import InMemoryLeadRepository, LeadRepository
from app.api.routers import crawl as crawl_router
from app.api.routers import leads
from app.api.routers.crawl import run_crawl_guarded
from app.api.security import RateLimiter
from app.api.ws import ConnectionManager, db_listener
from app.api.ws import router as ws_router
from app.config import Settings, get_settings


async def _crawl_scheduler(app: FastAPI) -> None:
    """Run the headless crawl once every crawl_interval_hours."""
    settings = app.state.settings
    interval = max(1, settings.crawl_interval_hours) * 3600
    try:
        if settings.crawl_on_start:
            await _safe_crawl(app)
        while True:
            await asyncio.sleep(interval)
            await _safe_crawl(app)
    except asyncio.CancelledError:
        raise


async def _safe_crawl(app: FastAPI) -> None:
    try:
        report = await run_crawl_guarded(app)
        if report is not None:
            logger.info('{"event": "scheduled_crawl", "persisted": %d, "fetched": %d}',
                        report.get("persisted", 0), report.get("fetched", 0))
    except Exception as exc:  # noqa: BLE001 - a bad crawl must not kill the scheduler
        logger.warning('{"event": "scheduled_crawl_error", "detail": "%s"}', exc)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Start the real-time push watcher (and, on Postgres, the crawl scheduler).
    # In-memory mode (tests, local) starts nothing.
    tasks = []
    settings = getattr(app.state, "settings", None)
    if settings and settings.use_mongo and settings.mongodb_uri:
        from app.api.mongo_repository import mongo_change_listener
        tasks.append(asyncio.create_task(mongo_change_listener(app)))
        if settings.crawl_enabled:
            tasks.append(asyncio.create_task(_crawl_scheduler(app)))
    elif settings and settings.use_db_repository:
        tasks.append(asyncio.create_task(db_listener(app)))
        if settings.crawl_enabled:
            tasks.append(asyncio.create_task(_crawl_scheduler(app)))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


def create_app(settings: Settings | None = None, repository: LeadRepository | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    # Only a live backing store needs the push watcher, so the in-memory app
    # (tests, local demo) runs without a lifespan.
    use_live = settings.use_db_repository or (settings.use_mongo and settings.mongodb_uri is not None)
    lifespan = _lifespan if use_live else None
    app = FastAPI(title="GovIntel Read API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.ws_manager = ConnectionManager()
    app.state.crawl_lock = asyncio.Lock()
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    if repository is None:
        if settings.use_mongo and settings.mongodb_uri:
            from app.api.mongo_repository import MongoLeadRepository
            repository = MongoLeadRepository(settings.mongodb_uri.get_secret_value(), settings.mongodb_db)
        elif settings.use_db_repository:
            from app.api.db_repository import SqlAlchemyLeadRepository
            from app.db.session import SessionLocal
            repository = SqlAlchemyLeadRepository(SessionLocal)
    app.state.repository = repository or InMemoryLeadRepository()

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    if settings.cors_origins:
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST"], allow_headers=["X-API-Key", "Content-Type"],
            allow_credentials=False,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException):
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(status_code=exc.status_code,
                            content={"error": exc.detail, "request_id": rid},
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        rid = getattr(request.state, "request_id", None)
        logger.exception("unhandled_error request_id=%s", rid)
        # Never leak internals to the client.
        return JSONResponse(status_code=500,
                            content={"error": "internal_error", "request_id": rid})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(leads.router)
    app.include_router(ws_router)
    app.include_router(crawl_router.router)

    # Serve the dashboard (same-origin) if the frontend directory is present.
    import os
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend"))
    if os.path.isdir(frontend_dir):
        from fastapi.staticfiles import StaticFiles
        app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="dashboard")

    return app
