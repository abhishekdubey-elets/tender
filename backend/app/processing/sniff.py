"""Content-type sniffing by magic bytes (authoritative), refined by declared
MIME / filename. Never trusts the declared type blindly — a portal that labels a
PDF ``text/html`` must still be classified as a PDF.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from app.processing.types import DocClass

_MIME_BY_CLASS = {
    DocClass.html: "text/html",
    DocClass.pdf: "application/pdf",
    DocClass.docx: "application/vnd.openxmlformats-officedocument.spreadsheetml.document",
    DocClass.xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    DocClass.doc: "application/msword",
    DocClass.xls: "application/vnd.ms-excel",
    DocClass.json: "application/json",
    DocClass.text: "text/plain",
}


@dataclass(slots=True)
class SniffResult:
    doc_class: DocClass
    mime: str | None
    note: str | None = None


def _classify_zip(content: bytes) -> DocClass:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = zf.namelist()
    except zipfile.BadZipFile:
        return DocClass.unknown
    if any(n.startswith("word/") for n in names):
        return DocClass.docx
    if any(n.startswith("xl/") for n in names):
        return DocClass.xlsx
    return DocClass.unknown


def _looks_like_text(content: bytes) -> bool:
    sample = content[:2048]
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    # Reject if it contains many control bytes (likely binary).
    control = sum(1 for b in sample if b < 9 or (13 < b < 32))
    return control <= max(1, len(sample) // 100)


def sniff(content: bytes, *, declared_mime: str | None = None, filename: str | None = None) -> SniffResult:
    if not content:
        return SniffResult(DocClass.unknown, None, "empty")

    head = content[:8]
    stripped = content.lstrip()[:512]
    ext = (filename or "").lower().rsplit(".", 1)[-1] if filename and "." in filename else ""

    # Binary signatures.
    if head.startswith(b"%PDF"):
        return SniffResult(DocClass.pdf, "application/pdf")
    if head.startswith(b"PK\x03\x04"):
        klass = _classify_zip(content)
        return SniffResult(klass, _MIME_BY_CLASS.get(klass), None if klass != DocClass.unknown else "zip")
    if head.startswith(b"\xd0\xcf\x11\xe0"):  # OLE2 compound (legacy .doc/.xls)
        if ext == "xls" or (declared_mime or "").endswith("ms-excel"):
            return SniffResult(DocClass.xls, "application/vnd.ms-excel", "legacy_ole")
        return SniffResult(DocClass.doc, "application/msword", "legacy_ole")

    # Text-ish signatures.
    if stripped[:1] in (b"{", b"["):
        return SniffResult(DocClass.json, "application/json")
    low = stripped.lower()
    if low.startswith(b"<!doctype html") or low.startswith(b"<html") or b"<html" in low[:256]:
        return SniffResult(DocClass.html, "text/html")

    if _looks_like_text(content):
        # Distinguish declared/extension hints among text formats.
        if ext == "json" or (declared_mime or "") == "application/json":
            return SniffResult(DocClass.json, "application/json")
        if ext in ("html", "htm") or (declared_mime or "").startswith("text/html"):
            return SniffResult(DocClass.html, "text/html")
        return SniffResult(DocClass.text, "text/plain")

    return SniffResult(DocClass.unknown, declared_mime, "unrecognized")
