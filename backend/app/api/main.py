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
from app.api.routers import leads
from app.api.security import RateLimiter
from app.api.ws import ConnectionManager, db_listener
from app.api.ws import router as ws_router
from app.config import Settings, get_settings


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Start the Postgres LISTEN/NOTIFY watcher only when a real DB is configured;
    # in-memory mode (tests, local) has no notify channel to listen on.
    task = None
    if getattr(app.state, "settings", None) and app.state.settings.use_db_repository:
        task = asyncio.create_task(db_listener(app))
    try:
        yield
    finally:
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


def create_app(settings: Settings | None = None, repository: LeadRepository | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    # Only the live DB server needs the LISTEN/NOTIFY watcher, so the in-memory
    # app (tests, local demo) runs without a lifespan.
    lifespan = _lifespan if settings.use_db_repository else None
    app = FastAPI(title="GovIntel Read API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.ws_manager = ConnectionManager()
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    if repository is None and settings.use_db_repository:
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

    # Serve the dashboard (same-origin) if the frontend directory is present.
    import os
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend"))
    if os.path.isdir(frontend_dir):
        from fastapi.staticfiles import StaticFiles
        app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="dashboard")

    return app
