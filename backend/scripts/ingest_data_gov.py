"""Ingestion runner for the data.gov.in (Open Government Data) API.

Official, documented, key-based JSON API — the sanctioned machine-access channel
(unlike CPPP/GeM scraping). It surfaces *scheme-level* signals (money allocated /
sanctioned to sectors and beneficiaries) filtered to the six Elets verticals.

Get a free API key at https://data.gov.in and set DATA_GOV_API_KEY in .env.

Discover datasets:   python -m scripts.ingest_data_gov --list "production linked"
Ingest one dataset:  python -m scripts.ingest_data_gov --resource <id> --vertical Pharma
Ingest a vertical:   python -m scripts.ingest_data_gov --vertical Pharma
Preview only:        python -m scripts.ingest_data_gov --vertical Pharma --dry-run
Continuously:        python -m scripts.ingest_data_gov --vertical Pharma --loop --interval 3600
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from app.config import get_settings
from app.db.session import SessionLocal
from app.ingestion.adapters.data_gov_in import VERTICAL_RESOURCES, DataGovInAdapter
from app.ingestion.db_sink import SqlAlchemySink
from app.ingestion.http_client import HttpClient
from app.ingestion.pipeline import IngestionReport, IngestionRunner
from app.ingestion.types import FetchedDocument, ParsedContent

CATALOG_URL = "https://api.data.gov.in/lists"


class _MemorySink:
    """In-memory sink for --dry-run: never touches the database."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()

    def exists(self, source_name: str, content_hash: str) -> bool:
        return (source_name, content_hash) in self._seen

    def store(self, document: FetchedDocument, parsed: ParsedContent | None) -> str:
        self._seen.add((document.source_name, document.content_hash))
        preview = document.content.decode("utf-8", errors="replace")[:110].replace("\n", " ")
        print(f"    - {preview}")
        return "dry-run"


def _resolve_key(args: argparse.Namespace) -> str:
    if args.api_key:
        return args.api_key
    secret = get_settings().data_gov_api_key
    if secret:
        return secret.get_secret_value()
    import os
    return os.environ.get("DATA_GOV_IN_API_KEY", "")


def _client() -> HttpClient:
    return HttpClient(user_agent="GovIntelBot/0.1 (+https://elets.in; contact: dme@elets.in)",
                      respect_robots=True, timeout=30.0)


def do_list(keyword: str, key: str) -> int:
    """Search the catalogue by title and print resource ids (index_name)."""
    with _client() as c:
        url = (f"{CATALOG_URL}?api-key={key}&format=json&limit=20"
               f"&filters[title]={keyword.replace(' ', '%20')}")
        resp = c.get(url)
    data = json.loads(resp.content.decode("utf-8"))
    records = data.get("records", [])
    print(f"data.gov.in datasets matching title ~ '{keyword}'  (total={data.get('total')}):")
    for r in records:
        print(f"  {r.get('index_name')}  {(r.get('title') or '').strip()[:80]}")
    if not records:
        print("  (none — try a different keyword)")
    return 0


def _ingest_resource(resource_id: str, vertical: str | None, key: str,
                     args: argparse.Namespace) -> IngestionReport:
    adapter = DataGovInAdapter(resource_id=resource_id, api_key=key, vertical=vertical)
    client = _client()
    t0 = time.perf_counter()
    try:
        if args.dry_run:
            runner = IngestionRunner(client, _MemorySink(), max_items=args.max_items)
            report = runner.run(adapter)
        else:
            session = SessionLocal()
            try:
                runner = IngestionRunner(client, SqlAlchemySink(session), max_items=args.max_items)
                report = runner.run(adapter)
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
    finally:
        client.close()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    label = f"{vertical or 'resource'}:{resource_id[:8]}"
    print(f"[{ts}] {label}: discovered={report.discovered} stored={report.stored} "
          f"dup={report.skipped_duplicate} robots={report.skipped_robots} "
          f"errors={len(report.errors)} ({(time.perf_counter()-t0)*1000:.0f} ms)")
    for url, msg in report.errors[:5]:
        print(f"    ! {url}: {msg}")
    return report


def _targets(args: argparse.Namespace) -> list[tuple[str, str | None]]:
    """Return (resource_id, vertical) pairs to ingest."""
    if args.resource:
        return [(args.resource, args.vertical)]
    if args.vertical:
        return [(rid, args.vertical) for rid, _title in VERTICAL_RESOURCES.get(args.vertical, ())]
    # all curated resources
    return [(rid, v) for v, items in VERTICAL_RESOURCES.items() for rid, _t in items]


def run_once(args: argparse.Namespace, key: str) -> bool:
    targets = _targets(args)
    if not targets:
        print(f"No datasets to ingest for vertical={args.vertical!r}. "
              f"Use --resource <id> or --list <keyword> to find one.", file=sys.stderr)
        return False
    ok = True
    for resource_id, vertical in targets:
        try:
            report = _ingest_resource(resource_id, vertical, key, args)
            ok = ok and report.ok
        except Exception as exc:  # noqa: BLE001
            print(f"    ! {resource_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
            ok = False
    return ok


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Ingest data.gov.in datasets, filtered to the ICP verticals.")
    p.add_argument("--list", metavar="KEYWORD", help="search the catalogue by title and print resource ids")
    p.add_argument("--resource", help="a specific dataset resource id (index_name)")
    p.add_argument("--vertical", help="one of the six ICP verticals (uses curated resources + keyword filter)")
    p.add_argument("--api-key", help="override the data.gov.in API key")
    p.add_argument("--max-items", type=int, default=None, help="cap records ingested per dataset")
    p.add_argument("--dry-run", action="store_true", help="fetch + parse but do not write to the database")
    p.add_argument("--loop", action="store_true", help="run continuously on an interval")
    p.add_argument("--interval", type=int, default=3600, help="seconds between runs in --loop (default 3600)")
    args = p.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    key = _resolve_key(args)
    if not key:
        print("error: no data.gov.in API key. Get a free key at https://data.gov.in and set "
              "DATA_GOV_API_KEY in .env (or pass --api-key).", file=sys.stderr)
        return 2

    if args.list:
        return do_list(args.list, key)

    if not args.loop:
        return 0 if run_once(args, key) else 1

    print(f"Starting data.gov.in ingestion loop every {args.interval}s (Ctrl-C to stop).")
    try:
        while True:
            try:
                run_once(args, key)
            except Exception as exc:  # noqa: BLE001
                print(f"    ! cycle failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            time.sleep(max(1, args.interval))
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
