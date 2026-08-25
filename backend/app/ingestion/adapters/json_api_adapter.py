"""Generic JSON API adapter with offset/limit pagination.

Subclasses provide the endpoint and how to read records out of the response;
pagination, rate limiting, retries and idempotency come from the framework.
Each record is stored as a JSON document.
"""
from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any, ClassVar

from app.ingestion.base import SourceAdapter
from app.ingestion.http_client import HttpClient
from app.ingestion.types import DiscoveredItem


class JSONApiAdapter(SourceAdapter):
    abstract = True
    parser_hint = "json"

    # Pagination configuration.
    page_size: ClassVar[int] = 100
    max_pages: ClassVar[int] = 1000  # hard safety cap
    # Path into the JSON body where the records list lives (e.g. ("records",)).
    records_path: ClassVar[tuple[str, ...]] = ()

    # -- subclasses override these -----------------------------------------
    def build_page_url(self, offset: int, limit: int) -> str:
        raise NotImplementedError

    def record_url(self, record: Any, offset: int, index: int) -> str:
        """Canonical URL for a record. Defaults to the page URL + row anchor."""
        return f"{self.build_page_url(offset, self.page_size)}#row={offset + index}"

    def record_ref(self, record: Any, offset: int, index: int) -> str | None:
        if isinstance(record, dict):
            for key in ("id", "_id", "uid", "reference", "ref"):
                if key in record:
                    return str(record[key])
        return f"{offset + index}"

    # -- shared logic -------------------------------------------------------
    def extract_records(self, data: Any) -> Sequence[Any]:
        node = data
        for key in self.records_path:
            node = node.get(key, []) if isinstance(node, dict) else []
        if isinstance(node, list):
            return node
        return []

    def discover(self, client: HttpClient) -> Iterator[DiscoveredItem]:
        offset = 0
        for _page in range(self.max_pages):
            url = self.build_page_url(offset, self.page_size)
            resp = client.get(url)
            data = json.loads(resp.content.decode("utf-8"))
            records = self.extract_records(data)
            if not records:
                return
            for index, record in enumerate(records):
                yield DiscoveredItem(
                    url=self.record_url(record, offset, index),
                    source_ref=self.record_ref(record, offset, index),
                    content_type_hint="json",
                    payload=record,
                )
            if len(records) < self.page_size:
                return
            offset += self.page_size
