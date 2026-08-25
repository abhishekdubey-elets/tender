"""Integration mapping tests: processing outcome → raw_documents fields + meta.

These use transient (session-less) ORM objects, so they validate the mapping
logic without needing a live database.
"""
from __future__ import annotations

import uuid

from app.db.enums import ParseStatus
from app.db.models import RawDocument
from app.processing import DocumentProcessor
from app.processing.db import apply_outcome_fields, build_processing_meta, load_source_file
from app.processing.types import ProcessingStatus, SourceFile
from tests.proc_fixtures import load_fixture


def _raw() -> RawDocument:
    return RawDocument(
        government_source_id=uuid.uuid4(),
        source_url="https://g.gov.in/doc",
        content_hash="deadbeef",
    )


def test_apply_success_outcome_to_raw_document() -> None:
    out = DocumentProcessor().process(
        SourceFile(load_fixture("sample.html"), "https://g.gov.in/x", declared_mime="text/html")
    )
    raw = _raw()
    apply_outcome_fields(raw, out)

    assert raw.parse_status is ParseStatus.parsed
    assert "Acme Infra" in raw.parsed_text
    assert raw.meta["processing"]["extraction_method"] == "html.beautifulsoup"
    assert raw.meta["processing"]["extraction_confidence"] == 0.98
    assert raw.meta["hashes"]["sha256"] == out.sha256
    assert raw.meta["document_metadata"]["title"] == "Tender Award Notice"


def test_apply_failed_outcome_records_error() -> None:
    out = DocumentProcessor().process(SourceFile(b"", "https://g.gov.in/empty"))
    raw = _raw()
    apply_outcome_fields(raw, out)

    assert raw.parse_status is ParseStatus.failed
    assert raw.parsed_text is None
    assert raw.meta["processing"]["error_kind"] == "invalid_file"


def test_needs_ocr_maps_to_skipped_status() -> None:
    from tests.proc_fixtures import make_blank_pdf

    out = DocumentProcessor().process(
        SourceFile(make_blank_pdf(), "https://g.gov.in/scan.pdf", declared_mime="application/pdf")
    )
    assert out.status is ProcessingStatus.needs_ocr
    raw = _raw()
    apply_outcome_fields(raw, out)
    assert raw.parse_status is ParseStatus.skipped


def test_build_processing_meta_shape() -> None:
    out = DocumentProcessor().process(
        SourceFile(load_fixture("sample.json"), "https://g.gov.in/j", declared_mime="application/json")
    )
    meta = build_processing_meta(out)
    assert meta["processing"]["status"] == "succeeded"
    assert meta["processing"]["doc_class"] == "json"
    assert "sha256" in meta["hashes"]


def test_load_source_file_from_inline_raw_document() -> None:
    raw = RawDocument(
        government_source_id=uuid.uuid4(),
        source_url="https://g.gov.in/inline",
        content_hash="abc",
        raw_content="hello world",
        mime_type="text/plain",
    )
    sf = load_source_file(raw)
    assert sf.content == b"hello world"
    assert sf.source_url == "https://g.gov.in/inline"
    assert sf.declared_mime == "text/plain"
    assert sf.source_name == "unknown"   # no government_source loaded on transient obj
