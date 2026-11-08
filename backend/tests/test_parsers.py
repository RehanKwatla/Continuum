"""Parser unit tests (PDF, Markdown, text, format detection)."""

from __future__ import annotations

import pytest

from app.services.file_parser import ParseError, parse_markdown, parse_pdf, parse_text
from app.utils.files import detect_actual_format, normalize_archive_path

LIMIT = 400_000


def test_pdf_parser_produces_page_segments(synthetic_pdf) -> None:
    document = parse_pdf(synthetic_pdf, "handover.pdf", limit=LIMIT)
    assert document.page_count == 2
    assert "billing service" in document.text
    assert [segment.location for segment in document.segments] == ["page 1", "page 2"]
    assert document.metadata["detected_format"] == "pdf"


def test_pdf_parser_rejects_non_pdf_payload() -> None:
    with pytest.raises(ParseError):
        parse_pdf(b"not really a pdf", "fake.pdf", limit=LIMIT)


def test_markdown_parser_detects_structure() -> None:
    text = "# Title\n\ntext\n\n```python\nprint(1)\n```\n\n[link](https://x.test)\n"
    document = parse_markdown(text, "doc.md", limit=LIMIT)
    assert document.metadata["heading_count"] == 1
    assert document.metadata["code_block_count"] == 1
    assert document.metadata["link_count"] == 1
    assert document.segments[0].location == "# Title"


def test_text_parser_records_lines() -> None:
    document = parse_text("line one\nline two\n", "notes.txt", limit=LIMIT)
    assert document.metadata["line_count"] >= 2
    assert document.segments[0].location.startswith("lines ")


def test_format_detection_prefers_content_over_extension() -> None:
    assert detect_actual_format(b"%PDF-1.7 hello", "notes.txt") == "pdf"
    assert detect_actual_format(b"PK\x03\x04", "notes.txt") == "zip"
    assert detect_actual_format(b"plain ascii", "mystery.dat") == "text"
    assert detect_actual_format(b"\x00\x01\x02binary", "mystery.dat") == "unknown"


def test_archive_path_normalisation_blocks_traversal() -> None:
    assert normalize_archive_path("docs/guide.md") == "docs/guide.md"
    assert normalize_archive_path("../escape.md") is None
    assert normalize_archive_path("/etc/passwd") is None
    assert normalize_archive_path("C:\\Windows\\evil.txt") is None
    assert normalize_archive_path("a/../../b.md") is None
