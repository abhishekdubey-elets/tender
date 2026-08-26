"""Repeatable Google-News → government-money leads CLI (thin wrapper over app.crawl).

Three ways to use it:

  # high-precision path (multi-agent extraction runs in Claude Code):
  python -m scripts.news_leads fetch --out cand.json
      → Workflow(scriptPath scripts/gnews_leads_workflow.js, args=cand.json) → leads.json
  python -m scripts.news_leads persist --leads leads.json

  # headless path (no model — conservative rule extractor), same as the API/scheduler:
  python -m scripts.news_leads crawl

See scripts/README_news_leads.md.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.crawl.service import fetch_candidates, persist_leads, run_crawl


def fetch(args: argparse.Namespace) -> int:
    by_sector = fetch_candidates(per_vertical=args.per_vertical)
    for vertical, items in by_sector.items():
        print(f"{vertical}: {len(items)} items")
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"bySector": by_sector}, fh, ensure_ascii=False)
    total = sum(len(v) for v in by_sector.values())
    print(f"\nWrote {total} candidates to {args.out}")
    print("Next: run scripts/gnews_leads_workflow.js on this file, then "
          "`python -m scripts.news_leads persist --leads <leads.json>`.")
    return 0


def persist(args: argparse.Namespace) -> int:
    with open(args.leads, encoding="utf-8") as fh:
        data = json.load(fh)
    leads = data.get("leads", data) if isinstance(data, dict) else data
    written = persist_leads(leads)
    print(f"Persisted {len(written)} news leads: {', '.join(written) or '(none — all duplicates)'}")
    return 0


def crawl(args: argparse.Namespace) -> int:
    report = run_crawl(per_vertical=args.per_vertical)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(description="Google-News government-money leads runner.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("fetch", help="fetch Google News per vertical -> candidates JSON")
    pf.add_argument("--out", default="leads_candidates.json")
    pf.add_argument("--per-vertical", type=int, default=12)
    pf.set_defaults(func=fetch)

    pp = sub.add_parser("persist", help="persist a leads JSON (workflow output) to Postgres")
    pp.add_argument("--leads", required=True)
    pp.set_defaults(func=persist)

    pc = sub.add_parser("crawl", help="headless fetch + rule-extract + persist (no model)")
    pc.add_argument("--per-vertical", type=int, default=10)
    pc.set_defaults(func=crawl)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
