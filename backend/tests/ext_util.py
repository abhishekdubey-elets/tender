"""Helpers for extraction tests."""
from __future__ import annotations

from datetime import datetime, timezone

from app.processing.types import DocClass, DocumentMetadata, NormalizedDocument

FIXED_NOW = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)


def fixed_now() -> datetime:
    return FIXED_NOW


def make_norm(text: str, *, url: str = "https://pib.gov.in/pr/1") -> NormalizedDocument:
    return NormalizedDocument(
        source_url=url,
        source_name="PIB",
        source_type="pib",
        fetched_at=FIXED_NOW,
        sha256="0" * 64,
        md5="0" * 32,
        byte_size=len(text.encode()),
        doc_class=DocClass.html,
        detected_mime="text/html",
        declared_mime="text/html",
        extraction_method="html.beautifulsoup",
        extraction_confidence=0.98,
        ocr_used=False,
        text=text,
        metadata=DocumentMetadata(),
    )


def event(**kw) -> dict:
    """Build an ExtractedEvent-shaped dict with sensible defaults."""
    base = {
        "event_type": "contract_award",
        "government_entity": None,
        "entities": [],
        "contract_value": None,
        "currency": None,
        "sector": None,
        "project": None,
        "award_date": None,
        "announcement_date": None,
        "location": None,
        "description": None,
        "evidence": [],
        "confidence": 0.8,
    }
    base.update(kw)
    return base


def envelope(*events: dict, summary: str | None = None) -> dict:
    return {"events": list(events), "document_summary": summary}
