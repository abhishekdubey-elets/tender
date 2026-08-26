"""FastAPI app factory."""
from __future__ import annotations

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
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None, repository: LeadRepository | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    app = FastAPI(title="GovIntel Read API", version="0.1.0")
    app.state.settings = settings
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
    return app
