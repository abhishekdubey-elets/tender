"""One-off / repeatable export: Postgres leads → MongoDB Atlas ``leads`` collection.

Reads every lead through the existing SqlAlchemyLeadRepository (so the documents are
exactly the summary+detail shape the API serves) and upserts them into Mongo. Run it
after standing up the cluster, then start the API with USE_MONGO=true.

Requires (in the git-ignored .env):
    MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>/?appName=Cluster0
    MONGODB_DB=govintel        # optional, defaults to govintel

Run:  python -m scripts.export_to_mongo
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.api.db_repository import SqlAlchemyLeadRepository
from app.api.mongo_repository import MongoLeadRepository
from app.config import get_settings
from app.db.models import Opportunity
from app.db.session import SessionLocal


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    settings = get_settings()
    if not settings.mongodb_uri:
        print("error: set MONGODB_URI in .env (and USE_MONGO=true to serve from it).", file=sys.stderr)
        return 2

    src = SqlAlchemyLeadRepository(SessionLocal)
    dst = MongoLeadRepository(settings.mongodb_uri.get_secret_value(), settings.mongodb_db)
    dst.ensure_indexes()

    with SessionLocal() as session:
        org_ids = [str(o) for o in session.scalars(select(Opportunity.organization_id).distinct())]

    total = 0
    for org in org_ids:
        summaries = src.list_leads(org, {})
        for summary in summaries:
            detail = src.get_lead(org, summary["id"])
            if detail:
                dst.upsert_lead(org, detail)
                total += 1
        print(f"{org}: {len(summaries)} leads")
    print(f"Exported {total} leads to MongoDB db '{settings.mongodb_db}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
