"""Modular government-data ingestion framework.

The framework is built around a single :class:`~app.ingestion.base.SourceAdapter`
interface. Adding a new government source means writing one adapter and
registering it — nothing else in the pipeline changes. The generic
:class:`~app.ingestion.pipeline.IngestionRunner` drives any adapter through
*discover → fetch → parse → store* using only that interface.

Cross-cutting concerns (rate limiting, retries, robots.txt, error handling) live
in :mod:`app.ingestion.http_client` and are shared by every adapter.
"""
from __future__ import annotations

from app.ingestion.base import SourceAdapter
from app.ingestion.pipeline import IngestionReport, IngestionRunner
from app.ingestion.registry import get_adapter, list_adapters, register_adapter
from app.ingestion.types import (
    DiscoveredItem,
    DocumentMetadata,
    FetchedDocument,
    ParsedContent,
)

__all__ = [
    "SourceAdapter",
    "IngestionRunner",
    "IngestionReport",
    "register_adapter",
    "get_adapter",
    "list_adapters",
    "DiscoveredItem",
    "DocumentMetadata",
    "FetchedDocument",
    "ParsedContent",
]
