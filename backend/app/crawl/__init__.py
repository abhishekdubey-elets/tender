"""Headless crawl service: Google News -> rule-extracted government-money leads.

Shared by the CLI (scripts/news_leads.py), the manual-crawl API endpoint, and the
24-hour scheduler. The high-precision extraction path is the multi-agent workflow
(scripts/gnews_leads_workflow.js); this module is the headless fallback that needs
no model — a conservative rule extractor (explicit amount + government counterparty,
hard-excluding stock/opinion/defence/foreign noise).
"""
from app.crawl.service import CrawlReport, persist_leads, run_crawl

__all__ = ["CrawlReport", "run_crawl", "persist_leads"]
