"""initial schema

Baseline migration for the government-event sales intelligence platform.

Approach: this baseline builds every table directly from the ORM metadata so
the migration and the models can never drift at the baseline. Subsequent
migrations are authored normally (``alembic revision --autogenerate``), which
diffs against the same metadata. Extensions are created first (pgvector needs
``vector``; UUID server defaults need ``pgcrypto``), and the approximate-nearest
-neighbour (HNSW) vector indexes — which are managed outside the ORM — are added
afterwards.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-25
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db.models import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Vector ANN indexes (cosine) — created outside the ORM metadata.
VECTOR_INDEXES = [
    (
        "ix_government_events_embedding_hnsw",
        "government_events",
        "embedding",
    ),
    (
        "ix_companies_name_embedding_hnsw",
        "companies",
        "name_embedding",
    ),
]


def upgrade() -> None:
    bind = op.get_bind()

    # Required extensions.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # All tables, enums, constraints and (non-vector) indexes from the models.
    Base.metadata.create_all(bind=bind)

    # HNSW indexes for semantic dedup / company matching.
    for index_name, table, column in VECTOR_INDEXES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} "
            f"ON {table} USING hnsw ({column} vector_cosine_ops)"
        )


def downgrade() -> None:
    bind = op.get_bind()

    for index_name, _table, _column in VECTOR_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")

    # Drops tables and the native enum types created above.
    Base.metadata.drop_all(bind=bind)
