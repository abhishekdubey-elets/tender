"""Real ingestion runner for PIB (Press Information Bureau) press releases.

This fetches the **live** PIB RSS feed over the network, parses each entry, and
persists it as a ``raw_documents`` row in Postgres — the real Stage 1 of the
pipeline. It is idempotent (documents are de-duplicated by content hash), polite
(robots-aware, rate-limited), and can run once or on a fixed interval for
near-real-time collection.

Run once:      python -m scripts.ingest_pib
Every 5 min:   python -m scripts.ingest_pib --loop --interval 300
Preview only:  python -m scripts.ingest_pib --dry-run --max-items 5

Notes
-----
* PIB sits behind a bot-WAF that 403s non-browser User-Agents and, intermittently,
  the ``robots.txt`` request itself. PIB publishes no real robots.txt (its
  ``/robots.txt`` is an HTML stub), so we send a browser-like UA and treat an
  *unavailable* robots.txt as unrestricted (RFC 9309 §2.3.1.3) — this is
  authorized collection of a feed published expressly for machines.
* This runner performs ingestion only (fetch → parse → store). Turning the stored
  documents into scored *leads* is the extraction stage, which needs a real
  Anthropic model (``ANTHROPIC_API_KEY``); once that runs, new opportunities are
  pushed to the dashboard instantly via the existing WebSocket layer.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from app.config import get_settings
from app.db.session import SessionLocal
from app.ingestion.adapters.pib import PIBPressReleaseAdapter
from app.ingestion.db_sink import SqlAlchemySink
from app.ingestion.http_client import HttpClient
from app.ingestion.pipeline import IngestionReport, IngestionRunner
from app.ingestion.retry import RetryPolicy
from app.ingestion.types import FetchedDocument, ParsedContent

# A browser-like UA that PIB's WAF accepts, with an honest bot identifier and
# contact appended (courtesy for server operators).
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "GovIntelBot/0.1 (+https://elets.in; contact: dme@elets.in)"
)


class _MemorySink:
    """In-memory sink for --dry-run: never touches the database."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()

    def exists(self, source_name: str, content_hash: str) -> bool:
        return (source_name, content_hash) in self._seen

    def store(self, document: FetchedDocument, parsed: ParsedContent | None) -> str:
        self._seen.add((document.source_name, document.content_hash))
        title = (parsed.title if parsed and parsed.title else document.metadata.title) or "(untitled)"
        print(f"    - {title[:80]}")
        return "dry-run"


def _build_client(user_agent: str) -> HttpClient:
    # PIB's WAF intermittently 403s otherwise-valid requests, so treat 403 as a
    # transient, retryable status (with backoff) rather than a hard failure.
    retry = RetryPolicy(
        max_attempts=5,
        base_backoff_seconds=1.0,
        retry_statuses=(403, 429, 500, 502, 503, 504),
    )
    # respect robots, but treat PIB's unavailable/WAF-403'd robots.txt as allowed.
    return HttpClient(
        user_agent=user_agent,
        respect_robots=True,
        robots_forbidden_is_disallow=False,
        retry_policy=retry,
        timeout=30.0,
    )


def _print_report(report: IngestionReport, elapsed_ms: float) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    print(
        f"[{ts}] {report.source_name}: "
        f"discovered={report.discovered} fetched={report.fetched} stored={report.stored} "
        f"dup={report.skipped_duplicate} robots={report.skipped_robots} "
        f"not_found={report.not_found} parse_fail={report.parse_failures} "
        f"errors={len(report.errors)} ({elapsed_ms:.0f} ms)"
    )
    for url, msg in report.errors[:10]:
        print(f"    ! {url}: {msg}")


def run_once(args: argparse.Namespace) -> IngestionReport:
    adapter = PIBPressReleaseAdapter()
    if args.feed:
        adapter.feed_url = args.feed  # type: ignore[misc]

    client = _build_client(args.user_agent)
    t0 = time.perf_counter()
    try:
        if args.dry_run:
            sink = _MemorySink()
            runner = IngestionRunner(client, sink, max_items=args.max_items)
            report = runner.run(adapter)
        else:
            session = SessionLocal()
            try:
                sink = SqlAlchemySink(session)
                runner = IngestionRunner(client, sink, max_items=args.max_items)
                report = runner.run(adapter)
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
    finally:
        client.close()
    _print_report(report, (time.perf_counter() - t0) * 1000)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest live PIB press releases into Postgres.")
    parser.add_argument("--loop", action="store_true", help="run continuously on an interval")
    parser.add_argument("--interval", type=int, default=300, help="seconds between runs in --loop (default 300)")
    parser.add_argument("--max-items", type=int, default=None, help="cap items fetched per run")
    parser.add_argument("--dry-run", action="store_true", help="fetch + parse but do not write to the database")
    parser.add_argument("--feed", default=None, help="override the PIB RSS feed URL")
    parser.add_argument("--user-agent", default=DEFAULT_UA, help="override the HTTP User-Agent")
    args = parser.parse_args(argv)

    # Government titles carry non-Latin-1 characters; keep console output from
    # crashing on Windows' default cp1252 stdout.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    settings = get_settings()
    if not args.dry_run and not settings.use_db_repository:
        # Not fatal — the API only serves DB data when this is true — but warn so
        # ingested docs aren't silently invisible to the dashboard.
        print("note: USE_DB_REPOSITORY is not enabled; the API won't serve this data until it is.",
              file=sys.stderr)

    if not args.loop:
        report = run_once(args)
        return 0 if report.ok else 1

    print(f"Starting PIB ingestion loop every {args.interval}s (Ctrl-C to stop).")
    try:
        while True:
            try:
                run_once(args)
            except Exception as exc:  # noqa: BLE001 - a bad cycle must not kill the loop
                print(f"    ! cycle failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            time.sleep(max(1, args.interval))
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
