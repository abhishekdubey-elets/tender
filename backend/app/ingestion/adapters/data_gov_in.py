"""data.gov.in (Open Government Data Platform India) JSON API adapter.

A clean, official, documented JSON API — a good second "easiest reliable"
source. It requires a free API key (supplied via ``DATA_GOV_IN_API_KEY`` or the
constructor). The key is used only in the request URL and is deliberately kept
out of the stored ``source_url`` so it is never persisted.

Reality note: data.gov.in is a catalogue of mostly *statistical* datasets, not a
live tender/award stream — so it is a source of **scheme-level** signals (money
allocated/sanctioned to a sector or beneficiary) rather than "company X won a
contract today". The strongest fit for our ICP are the *beneficiary/sanctioned*
datasets (e.g. PLI projects sanctioned). Live contract-award data lives in
CPPP/GeM, which are not covered here.

Each dataset is a *resource* identified by an ``index_name`` (UUID). Resource ids
are discovered via ``https://api.data.gov.in/lists`` (see ``scripts/ingest_data_gov.py``).
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any, ClassVar

from app.db.enums import GovSourceType
from app.ingestion.adapters.json_api_adapter import JSONApiAdapter
from app.ingestion.http_client import HttpClient
from app.ingestion.rate_limiter import RateLimitConfig
from app.ingestion.registry import register_adapter
from app.ingestion.types import DiscoveredItem

# Keyword sets used to keep only records relevant to the six Elets verticals.
# Matched case-insensitively against the whole record text.
VERTICAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "e-Governance": ("e-governance", "egov", "digital india", "digital service",
                     "citizen service", "digilocker", "umang", "digital village"),
    "Digital Learning": ("education", "school", "edtech", "e-learning", "learning",
                         "samagra shiksha", "skill", "literacy", "nep"),
    "Pharma": ("pharma", "drug", "bulk drug", "api ", "production linked", "pli",
               "bulk drugs", "medicine", "vaccine"),
    "eHealth": ("health", "hospital", "ayushman", "abdm", "abha", "telemedicine",
                "medical", "clinic", "national health mission", "nhm"),
    "Banking": ("bank", "credit", "lending", "core banking", "psb", "rrb"),
    "Finance": ("finance", "financial", "dbt", "treasury", "payment", "fintech",
                "insurance", "pension", "subsidy", "gst"),
}

# Curated candidate resource ids discovered live on data.gov.in, grouped by
# vertical. These are STARTING POINTS — not every catalogue entry is API-enabled,
# and titles/schemas vary; verify with your key via `ingest_data_gov.py --list`.
VERTICAL_RESOURCES: dict[str, tuple[tuple[str, str], ...]] = {
    "Pharma": (
        ("7ee6af27-f59f-4e02-a3d6-e33b814efec7", "Beneficiary-wise Projects Sanctioned under PLI"),
        ("748b3b88-840d-4767-91f2-fe42f632697e", "State/UT-wise Applications Approved under PLI"),
    ),
    "eHealth": (
        ("fd04da2e-d8e2-4b15-a23c-009784ccbeda", "State/UT-wise Funds Allocated & Released under NHM"),
        ("3b701b29-bdf7-4e95-b611-8d70e1b9ab74", "Year-wise Total ABHAs Created"),
    ),
    # e-Governance / Digital Learning / Banking / Finance: fewer clean award-style
    # datasets on data.gov.in; use `--list <keyword>` to source resource ids.
}


@register_adapter
class DataGovInAdapter(JSONApiAdapter):
    name = "data.gov.in Open Data"
    source_type = GovSourceType.api
    base_url = "https://api.data.gov.in/"
    rate_limit = RateLimitConfig(min_interval_seconds=1.0)
    records_path: ClassVar[tuple[str, ...]] = ("records",)
    page_size = 100
    # Official structured open-data API (see app/scoring/source_authority.py).
    source_authority: ClassVar[float] = 0.95

    requires_api_key: ClassVar[bool] = True

    def __init__(
        self,
        resource_id: str | None = None,
        api_key: str | None = None,
        *,
        keywords: tuple[str, ...] = (),
        vertical: str | None = None,
    ) -> None:
        self.resource_id = resource_id or os.environ.get("DATA_GOV_IN_RESOURCE_ID", "")
        self.api_key = api_key or os.environ.get("DATA_GOV_IN_API_KEY", "")
        self.vertical = vertical
        # Explicit keywords win; otherwise derive from the vertical.
        self.keywords = tuple(k.lower() for k in (keywords or VERTICAL_KEYWORDS.get(vertical or "", ())))

    def build_page_url(self, offset: int, limit: int) -> str:
        # api-key is required by the service in the query string; not stored.
        return (
            f"https://api.data.gov.in/resource/{self.resource_id}"
            f"?api-key={self.api_key}&format=json&offset={offset}&limit={limit}"
        )

    def record_url(self, record: Any, offset: int, index: int) -> str:
        # Key-free, human-facing URL persisted as provenance.
        return f"https://data.gov.in/resource/{self.resource_id}#row={offset + index}"

    def _matches(self, record: Any) -> bool:
        if not self.keywords:
            return True
        blob = json.dumps(record, ensure_ascii=False, default=str).lower()
        return any(kw in blob for kw in self.keywords)

    def discover(self, client: HttpClient) -> Iterator[DiscoveredItem]:
        # Keep only records relevant to the configured vertical/keywords.
        for item in super().discover(client):
            if self._matches(item.payload):
                yield item
