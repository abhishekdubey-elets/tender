"""Test fixtures.

The test schema is built by running the *real* Alembic migration against the
dedicated test database, so every test run also validates that the migration
applies (and, at teardown, that it downgrades cleanly). Each test then runs
inside a transaction that is rolled back for isolation.
"""
from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterator

# Windows' default ProactorEventLoop crashes (access violation in _write_to_self)
# under Starlette's TestClient blocking portal. Force a Selector loop for the
# portal by injecting a loop_factory; test-infra only, no production effect.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import anyio.from_thread as _aft

    _orig_start_portal = _aft.start_blocking_portal

    def _selector_start_portal(backend: str = "asyncio", backend_options: dict | None = None):
        if backend == "asyncio":
            backend_options = dict(backend_options or {})
            backend_options.setdefault("loop_factory", asyncio.SelectorEventLoop)
        return _orig_start_portal(backend=backend, backend_options=backend_options)

    _aft.start_blocking_portal = _selector_start_portal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.config import get_settings

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/


def _alembic_config(url: str) -> Config:
    cfg = Config(os.path.join(HERE, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture(scope="session")
def db_url() -> str:
    return get_settings().test_database_url


@pytest.fixture(scope="session")
def engine(db_url: str) -> Iterator[Engine]:
    eng = create_engine(db_url, future=True)
    # Defensive: ensure extensions exist even if the DB was created manually.
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    cfg = _alembic_config(db_url)
    # Clean slate, then apply the migration to build the schema.
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    yield eng

    command.downgrade(cfg, "base")
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Function-scoped session wrapped in a transaction rolled back after each test."""
    connection = engine.connect()
    trans = connection.begin()
    sess = Session(bind=connection, expire_on_commit=False)
    try:
        yield sess
    finally:
        sess.close()
        # A test that triggered an IntegrityError may have already invalidated the
        # transaction; only roll back if it is still active.
        if trans.is_active:
            trans.rollback()
        connection.close()
