"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings. DB values are needed by the schema layer; the rest
    configure the API, security and retention policy."""

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

    # --- API / security ---
    # Map of API key -> "<organization_id>:<role>". Empty by default: with no
    # keys configured, every request is rejected (fail closed).
    api_keys: dict[str, str] = {}
    cors_origins: list[str] = []
    rate_limit_per_minute: int = 120
    # When true, the API serves live data from Postgres via SqlAlchemyLeadRepository;
    # otherwise it uses the in-memory demo repository.
    use_db_repository: bool = False

    # --- secrets (never logged; SecretStr redacts on repr) ---
    anthropic_api_key: SecretStr | None = None
    voyage_api_key: SecretStr | None = None

    # --- retention / privacy (India DPDP) ---
    contact_retention_days: int = 365
    raw_document_retention_days: int = 730


@lru_cache
def get_settings() -> Settings:
    return Settings()
