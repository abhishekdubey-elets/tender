"""Test fixtures.

The test schema is built by running the *real* Alembic migration against the
dedicated test database, so every test run also validates that the migration
applies (and, at teardown, that it downgrades cleanly). Each test then runs
inside a transaction that is rolled back for isolation.
"""
from __future__ import annotations

import os
from collections.abc import Iterator

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
        trans.rollback()
        connection.close()
