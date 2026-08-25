"""Structural tests: the migration produces the expected physical schema."""
from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

EXPECTED_TABLES = {
    "organizations",
    "users",
    "target_sectors",
    "products",
    "product_target_sectors",
    "government_sources",
    "raw_documents",
    "government_events",
    "event_sources",
    "companies",
    "company_aliases",
    "company_enrichment",
    "contacts",
    "opportunities",
    "opportunity_evidence",
    "lead_scores",
    "sales_briefs",
    "outreach",
    "sales_feedback",
    "processing_jobs",
    "audit_logs",
    "alembic_version",
}


def test_all_tables_created(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= tables, f"missing: {EXPECTED_TABLES - tables}"


def test_extensions_installed(engine: Engine) -> None:
    with engine.connect() as conn:
        exts = {row[0] for row in conn.exec_driver_sql("SELECT extname FROM pg_extension")}
    assert "vector" in exts
    assert "pgcrypto" in exts


def test_source_url_is_not_null(engine: Engine) -> None:
    """Provenance guarantee: the original government URL can never be lost."""
    cols = {c["name"]: c for c in inspect(engine).get_columns("raw_documents")}
    assert cols["source_url"]["nullable"] is False
    es_cols = {c["name"]: c for c in inspect(engine).get_columns("event_sources")}
    assert es_cols["source_url"]["nullable"] is False


def test_vector_columns_exist(engine: Engine) -> None:
    ev_cols = {c["name"] for c in inspect(engine).get_columns("government_events")}
    co_cols = {c["name"] for c in inspect(engine).get_columns("companies")}
    assert "embedding" in ev_cols
    assert "name_embedding" in co_cols


def test_hnsw_indexes_exist(engine: Engine) -> None:
    insp = inspect(engine)
    ev_idx = {i["name"] for i in insp.get_indexes("government_events")}
    co_idx = {i["name"] for i in insp.get_indexes("companies")}
    assert "ix_government_events_embedding_hnsw" in ev_idx
    assert "ix_companies_name_embedding_hnsw" in co_idx


def test_confidence_check_constraints_present(engine: Engine) -> None:
    insp = inspect(engine)
    checks = {c["name"] for c in insp.get_check_constraints("government_events")}
    assert "ck_government_events_confidence_range" in checks
