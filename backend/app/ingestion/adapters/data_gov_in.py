"""data.gov.in (Open Government Data Platform India) JSON API adapter.

A clean, official, documented JSON API — a good second "easiest reliable"
source. It requires a free API key (supplied via ``DATA_GOV_IN_API_KEY`` or the
constructor). The key is used only in the request URL and is deliberately kept
out of the stored ``source_url`` so it is never persisted.
"""
from __future__ import annotations

import os
from typing import Any, ClassVar

from app.db.enums import GovSourceType
from app.ingestion.adapters.json_api_adapter import JSONApiAdapter
from app.ingestion.rate_limiter import RateLimitConfig
from app.ingestion.registry import register_adapter


@register_adapter
class DataGovInAdapter(JSONApiAdapter):
    name = "data.gov.in Open Data"
    source_type = GovSourceType.api
    base_url = "https://api.data.gov.in/"
    rate_limit = RateLimitConfig(min_interval_seconds=1.0)
    records_path: ClassVar[tuple[str, ...]] = ("records",)
    page_size = 100

    requires_api_key: ClassVar[bool] = True

    def __init__(self, resource_id: str | None = None, api_key: str | None = None) -> None:
        self.resource_id = resource_id or os.environ.get("DATA_GOV_IN_RESOURCE_ID", "")
        self.api_key = api_key or os.environ.get("DATA_GOV_IN_API_KEY", "")

    def build_page_url(self, offset: int, limit: int) -> str:
        # api-key is required by the service in the query string; not stored.
        return (
            f"https://api.data.gov.in/resource/{self.resource_id}"
            f"?api-key={self.api_key}&format=json&offset={offset}&limit={limit}"
        )

    def record_url(self, record: Any, offset: int, index: int) -> str:
        # Key-free, human-facing URL persisted as provenance.
        return f"https://data.gov.in/resource/{self.resource_id}#row={offset + index}"
