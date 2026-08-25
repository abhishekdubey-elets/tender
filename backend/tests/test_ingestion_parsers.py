"""Parser tests for every supported content type (mocked/synthetic inputs)."""
from __future__ import annotations

import io

from openpyxl import Workbook

from app.ingestion.parsers import detect_kind, parse_document
from app.ingestion.types import DocumentMetadata, FetchedDocument

RSS_XML = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Gov Feed</title>
<item><title>Award A</title><link>https://g.gov.in/a</link><description>won contract</description></item>
<item><title>Award B</title><link>https://g.gov.in/b</link><description>funding released</description></item>
</channel></rss>"""


def _doc(content: bytes, mime: str | None = None, url: str = "https://g.gov.in/x") -> FetchedDocument:
    return FetchedDocument(
        source_name="s", source_type="api", source_url=url, content=content,
        metadata=DocumentMetadata(content_type=mime),
    )


def test_parse_html() -> None:
    doc = _doc(
        b"<html><head><title>Tender</title></head><body><p>Hello</p><script>bad()</script></body></html>",
        "text/html",
    )
    parsed = parse_document(doc)
    assert parsed.parser_name == "html"
    assert "Hello" in parsed.text
    assert "bad()" not in parsed.text
    assert parsed.title == "Tender"


def test_parse_json() -> None:
    parsed = parse_document(_doc(b'{"awardee": "Acme", "value": 100}', "application/json"))
    assert parsed.structured == {"awardee": "Acme", "value": 100}


def test_parse_rss() -> None:
    parsed = parse_document(_doc(RSS_XML, "application/rss+xml"))
    assert parsed.parser_name == "rss"
    assert len(parsed.structured) == 2
    assert parsed.structured[0]["title"] == "Award A"


def test_parse_csv() -> None:
    parsed = parse_document(_doc(b"awardee,value\nAcme,100\n", "text/csv"))
    assert parsed.structured == [["awardee", "value"], ["Acme", "100"]]


def test_parse_excel() -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["awardee", "value"])
    ws.append(["Acme Infra", 5000000])
    buf = io.BytesIO()
    wb.save(buf)
    parsed = parse_document(
        _doc(buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    )
    assert parsed.parser_name == "excel"
    sheet = next(iter(parsed.structured.values()))
    assert sheet[0] == ["awardee", "value"]
    assert sheet[1][0] == "Acme Infra"


def test_parse_pdf_text_layer() -> None:
    doc = _doc(b"%PDF-1.4 fake", "application/pdf")
    parsed = parse_document(doc, pdf_text_backend=lambda _b: "Contract awarded to Acme Infra Pvt Ltd")
    assert parsed.parser_name == "pdf"
    assert "Acme Infra" in parsed.text
    assert parsed.extra["scanned"] is False


def test_parse_scanned_pdf_without_engine_flags_for_ocr() -> None:
    doc = _doc(b"%PDF-1.4 scanned", "application/pdf")
    parsed = parse_document(doc, pdf_text_backend=lambda _b: "   ")  # empty text layer
    assert parsed.extra["scanned"] is True
    assert parsed.extra["needs_ocr"] is True
    assert parsed.text is None


def test_parse_scanned_pdf_with_ocr_engine() -> None:
    doc = _doc(b"%PDF-1.4 scanned", "application/pdf")
    parsed = parse_document(
        doc,
        pdf_text_backend=lambda _b: "",             # no text layer
        ocr_engine=lambda _b: "OCR: work order to Beta Ltd",
    )
    assert parsed.parser_name == "pdf_ocr"
    assert "Beta Ltd" in parsed.text


def test_detect_kind_by_sniffing() -> None:
    assert detect_kind(_doc(b"%PDF-1.7 ...", None)) == "pdf"
    assert detect_kind(_doc(b'{"a":1}', None)) == "json"
    assert detect_kind(_doc(b"PK\x03\x04rest", None)) == "xlsx"
    assert detect_kind(_doc(b"<html><body>x", None)) == "html"


def test_hint_overrides_detection() -> None:
    doc = _doc(b'{"x":1}', "text/html")  # misleading mime
    parsed = parse_document(doc, hint="json")
    assert parsed.structured == {"x": 1}
