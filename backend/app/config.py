"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings. Only DB-related values are needed for the schema layer."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Primary application database.
    database_url: str = (
        "postgresql+psycopg://govintel:govintel@localhost:5432/govintel"
    )

    # Separate database used by the test-suite (safe to drop/recreate).
    test_database_url: str = (
        "postgresql+psycopg://govintel:govintel@localhost:5432/govintel_test"
    )

    sql_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
