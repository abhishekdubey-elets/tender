"""Document-processing pipeline tests with representative fixtures."""
from __future__ import annotations

from app.processing import DocumentProcessor
from app.processing.dedup import DuplicateIndex
from app.processing.extractors import ExtractionContext, OcrResult
from app.processing.types import DocClass, Method, ProcessingStatus, SourceFile
from tests.proc_fixtures import load_fixture, make_blank_pdf, make_docx, make_xlsx


def _src(content: bytes, url: str = "https://g.gov.in/doc", **kw) -> SourceFile:
    return SourceFile(content=content, source_url=url, source_name="Test", **kw)


def proc(**kw) -> DocumentProcessor:
    return DocumentProcessor(**kw)


# --- validation --------------------------------------------------------------
def test_empty_file_is_failed_not_discarded() -> None:
    out = proc().process(_src(b""))
    assert out.status is ProcessingStatus.failed
    assert out.error_kind == "invalid_file"
    assert out.sha256  # hash still computed


def test_oversize_file_is_failed() -> None:
    out = proc(max_bytes=10).process(_src(b"x" * 100, declared_mime="text/plain"))
    assert out.status is ProcessingStatus.failed
    assert "too_large" in out.error


def test_unrecognized_binary_is_failed_not_discarded() -> None:
    out = proc().process(_src(b"\x00\x01\x02\x03rubbish\xff\xfe"))
    assert out.status is ProcessingStatus.failed
    assert out.error == "unrecognized_format"


# --- extraction per type -----------------------------------------------------
def test_html() -> None:
    out = proc().process(_src(load_fixture("sample.html"), declared_mime="text/html"))
    assert out.is_success
    n = out.normalized
    assert n.doc_class is DocClass.html
    assert n.extraction_method == Method.HTML_BS4
    assert "Acme Infra" in n.text
    assert "var x" not in n.text            # scripts stripped
    assert n.metadata.title == "Tender Award Notice"
    assert n.extraction_confidence == 0.98


def test_json() -> None:
    out = proc().process(_src(load_fixture("sample.json"), declared_mime="application/json"))
    assert out.is_success
    assert out.normalized.doc_class is DocClass.json
    assert out.normalized.extraction_method == Method.JSON
    assert "Acme Infra Pvt Ltd" in out.normalized.text


def test_plain_text() -> None:
    out = proc().process(_src(load_fixture("sample.txt"), declared_mime="text/plain"))
    assert out.is_success
    assert out.normalized.doc_class is DocClass.text
    assert "Smart Cities Mission" in out.normalized.text


def test_docx() -> None:
    out = proc().process(_src(make_docx(), filename="award.docx"))
    assert out.is_success
    n = out.normalized
    assert n.doc_class is DocClass.docx
    assert n.extraction_method == Method.DOCX
    assert "Beta Constructions Ltd" in n.text
    assert "7500000" in n.text               # table cell text
    assert n.metadata.title == "Award Order"
    assert n.metadata.author == "MoHUA"


def test_xlsx() -> None:
    out = proc().process(_src(make_xlsx(), filename="awards.xlsx"))
    assert out.is_success
    n = out.normalized
    assert n.doc_class is DocClass.xlsx
    assert n.extraction_method == Method.XLSX
    assert "Gamma Systems Pvt Ltd" in n.text
    assert n.metadata.sheet_names == ["Awards"]


# --- PDF: text, scanned, OCR -------------------------------------------------
def test_pdf_with_text_layer() -> None:
    ctx = ExtractionContext(pdf_text_backend=lambda _c: "Contract awarded to Delta Ltd " * 20)
    out = proc(context=ctx).process(_src(make_blank_pdf(), declared_mime="application/pdf"))
    assert out.is_success
    n = out.normalized
    assert n.doc_class is DocClass.pdf
    assert n.extraction_method == Method.PDF_TEXT
    assert n.ocr_used is False
    assert 0.6 <= n.extraction_confidence <= 0.95
    assert n.metadata.page_count == 1        # real pypdf metadata


def test_scanned_pdf_without_engine_needs_ocr() -> None:
    # Blank PDF has no text layer and no OCR engine configured.
    out = proc().process(_src(make_blank_pdf(), declared_mime="application/pdf"))
    assert out.status is ProcessingStatus.needs_ocr
    n = out.normalized
    assert n.doc_class is DocClass.pdf_scanned
    assert n.ocr_used is False
    assert n.text is None


def test_scanned_pdf_with_ocr_engine() -> None:
    ctx = ExtractionContext(ocr_engine=lambda _c: OcrResult(text="OCR: award to Zeta", confidence=0.82))
    out = proc(context=ctx).process(_src(make_blank_pdf(), declared_mime="application/pdf"))
    assert out.is_success
    n = out.normalized
    assert n.doc_class is DocClass.pdf_scanned
    assert n.extraction_method == Method.PDF_OCR
    assert n.ocr_used is True
    assert n.extraction_confidence == 0.82
    assert "Zeta" in n.text


# --- unsupported & malformed -------------------------------------------------
def test_legacy_doc_is_unsupported_not_discarded() -> None:
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64
    out = proc().process(_src(ole, filename="old.doc"))
    assert out.status is ProcessingStatus.failed
    assert out.error_kind == "unsupported"


def test_malformed_office_zip_is_failed_not_discarded() -> None:
    fake_zip = b"PK\x03\x04" + b"\x00" * 40   # zip magic but not a valid archive
    out = proc().process(_src(fake_zip, filename="broken.docx"))
    assert out.status is ProcessingStatus.failed
    # sniff can't identify it -> validation rejects it (still hashed, not dropped)
    assert out.sha256


# --- hashing & duplicate detection ------------------------------------------
def test_hash_is_stable_and_duplicates_detected() -> None:
    index = DuplicateIndex()
    processor = proc(duplicate_index=index)
    content = load_fixture("sample.json")

    first = processor.process(_src(content, declared_mime="application/json"))
    assert first.is_success
    assert first.duplicate_of is None

    second = processor.process(_src(content, declared_mime="application/json"))
    assert second.duplicate_of == first.sha256      # same content → duplicate
    assert first.sha256 == second.sha256


def test_md5_and_bytesize_recorded() -> None:
    out = proc().process(_src(load_fixture("sample.txt"), declared_mime="text/plain"))
    assert len(out.normalized.md5) == 32
    assert out.normalized.byte_size == len(load_fixture("sample.txt"))
