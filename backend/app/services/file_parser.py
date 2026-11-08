"""Parsers that turn raw artefacts into text + locatable segments.

Supported: PDF (PyMuPDF), Markdown, plain text and ZIP archive members.
No uploaded file is ever executed; PDFs are read as data streams only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pymupdf

from app.utils.text import normalize_text, truncate_content

MAX_LINES_PER_SEGMENT = 50


class ParseError(Exception):
    """Raised when an artefact cannot be parsed safely."""


@dataclass
class ParsedSegment:
    """A locatable slice of a parsed document (page, heading section, line range)."""

    location: str
    text: str
    start_offset: int
    end_offset: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    text: str
    segments: list[ParsedSegment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    page_count: int | None = None

    @property
    def warnings(self) -> list[str]:
        return list(self.metadata.get("parse_warnings") or [])


def _finalise(
    raw_text: str, segments: list[ParsedSegment], metadata: dict[str, Any], limit: int
) -> ParsedDocument:
    content, truncated = truncate_content(normalize_text(raw_text), limit)
    if truncated:
        metadata.setdefault("parse_warnings", []).append(
            f"Content was truncated to {limit} characters for processing."
        )
        content = f"{content}\n\n[truncated]"
    return ParsedDocument(
        text=content,
        segments=segments,
        metadata=metadata,
        page_count=metadata.get("page_count"),
    )


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def parse_pdf(data: bytes, filename: str, *, limit: int) -> ParsedDocument:
    if not data.startswith(b"%PDF-"):
        raise ParseError("File does not start with a PDF header.")

    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # pragma: no cover - depends on PyMuPDF internals
        raise ParseError(f"Unable to open PDF: {type(exc).__name__}") from exc

    try:
        if getattr(document, "needs_pass", False):
            raise ParseError("PDF is password protected and cannot be processed.")

        page_texts: list[str] = []
        for page in document:
            try:
                page_texts.append(page.get_text("text") or "")
            except Exception:
                page_texts.append("")

        parts: list[str] = []
        segments: list[ParsedSegment] = []
        offset = 0
        for index, text in enumerate(page_texts, start=1):
            segments.append(
                ParsedSegment(
                    location=f"page {index}",
                    text=text,
                    start_offset=offset,
                    end_offset=offset + len(text),
                    metadata={"page": index},
                )
            )
            parts.append(text)
            offset += len(text) + 1

        raw_meta = dict(document.metadata or {})
        metadata: dict[str, Any] = {
            "page_count": document.page_count,
            "document_title": raw_meta.get("title") or None,
            "document_author": raw_meta.get("author") or None,
            "document_subject": raw_meta.get("subject") or None,
            "document_creator": raw_meta.get("creator") or None,
            "document_producer": raw_meta.get("producer") or None,
            "detected_format": "pdf",
            "original_filename": filename,
            "parse_warnings": [],
        }
        if not any(text.strip() for text in page_texts):
            metadata["parse_warnings"].append(
                "No selectable text found; the PDF may be a scanned image."
            )
        return _finalise("\n".join(parts), segments, metadata, limit)
    finally:
        document.close()


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$", re.MULTILINE)
_FENCE_RE = re.compile(r"^```[^\n`]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
_LINK_RE = re.compile(r"\[([^\]\n]{1,200})\]\(([^)\s]{1,500})\)")
_LIST_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\S", re.MULTILINE)


def parse_markdown(text: str, filename: str, *, limit: int) -> ParsedDocument:
    normalized = normalize_text(text)
    headings = [
        {"level": len(match.group(1)), "text": match.group(2).strip(), "line": _line_of(normalized, match.start())}
        for match in _HEADING_RE.finditer(normalized)
    ]
    code_blocks = [match.group(1) for match in _FENCE_RE.finditer(normalized)]
    links = [
        {"label": match.group(1), "url": match.group(2)}
        for match in _LINK_RE.finditer(normalized)
    ]

    segments: list[ParsedSegment] = []
    heading_matches = list(_HEADING_RE.finditer(normalized))
    if not heading_matches:
        segments = _line_segments(normalized)
    else:
        if heading_matches[0].start() > 0:
            preamble = normalized[: heading_matches[0].start()]
            segments.append(
                ParsedSegment("preamble", preamble, 0, len(preamble), {"heading": None})
            )
        for index, match in enumerate(heading_matches):
            start = match.start()
            end = (
                heading_matches[index + 1].start()
                if index + 1 < len(heading_matches)
                else len(normalized)
            )
            title = match.group(2).strip() or f"heading {len(segments) + 1}"
            segments.append(
                ParsedSegment(
                    location=f"# {title}",
                    text=normalized[start:end],
                    start_offset=start,
                    end_offset=end,
                    metadata={"heading_level": len(match.group(1)), "heading": title},
                )
            )

    metadata: dict[str, Any] = {
        "detected_format": "markdown",
        "original_filename": filename,
        "heading_count": len(headings),
        "headings": headings[:100],
        "code_block_count": len(code_blocks),
        "link_count": len(links),
        "links": links[:100],
        "list_item_count": len(_LIST_RE.findall(normalized)),
        "line_count": normalized.count("\n") + 1,
        "parse_warnings": [],
    }
    return _finalise(normalized, segments, metadata, limit)


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------
def parse_text(text: str, filename: str, *, limit: int) -> ParsedDocument:
    normalized = normalize_text(text)
    lines = normalized.split("\n")
    segments = _line_segments(normalized)

    metadata: dict[str, Any] = {
        "detected_format": "text",
        "original_filename": filename,
        "line_count": len(lines),
        "word_count": len(normalized.split()),
        "character_count": len(normalized),
        "parse_warnings": [],
    }
    return _finalise(normalized, segments, metadata, limit)


def parse_plaintext_like(text: str, filename: str, *, limit: int, fmt: str) -> ParsedDocument:
    if fmt == "markdown":
        return parse_markdown(text, filename, limit=limit)
    return parse_text(text, filename, limit=limit)


def _line_segments(text: str) -> list[ParsedSegment]:
    segments: list[ParsedSegment] = []
    offset = 0
    lines = text.split("\n")
    for start_line in range(0, len(lines), MAX_LINES_PER_SEGMENT):
        block = lines[start_line : start_line + MAX_LINES_PER_SEGMENT]
        block_text = "\n".join(block)
        segments.append(
            ParsedSegment(
                location=f"lines {start_line + 1}-{start_line + len(block)}",
                text=block_text,
                start_offset=offset,
                end_offset=offset + len(block_text),
                metadata={"first_line": start_line + 1, "last_line": start_line + len(block)},
            )
        )
        offset += len(block_text) + 1
    return segments


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def decode_text_bytes(payload: bytes) -> str:
    """Decode text content, tolerating BOMs and non-UTF8 encodings."""
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return payload.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return payload.decode("utf-8", errors="replace")
