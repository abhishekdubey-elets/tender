"""Concrete source adapters.

Importing this package imports every concrete adapter module, which triggers
their ``@register_adapter`` decorators. The pipeline discovers adapters through
the registry, so this is the only place that needs to know they exist.
"""
from __future__ import annotations

from app.ingestion.adapters import data_gov_in, pib  # noqa: F401  (self-registration)
from app.ingestion.adapters.json_api_adapter import JSONApiAdapter
from app.ingestion.adapters.rss_adapter import RSSAdapter

__all__ = ["RSSAdapter", "JSONApiAdapter", "pib", "data_gov_in"]
