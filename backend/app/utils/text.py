"""Text normalisation helpers."""

from __future__ import annotations

import re
import unicodedata

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def strip_control_characters(value: str) -> str:
    return _CONTROL_CHARS.sub("", value)


def collapse_blank_lines(value: str) -> str:
    return _MULTI_BLANK_LINES.sub("\n\n", value)


def normalize_text(value: str) -> str:
    """Canonicalise Unicode + whitespace without destroying code indentation."""
    value = unicodedata.normalize("NFKC", value)
    value = normalize_newlines(value)
    value = strip_control_characters(value)
    value = collapse_blank_lines(value)
    return value.strip("\n")


def truncate_content(value: str, limit: int) -> tuple[str, bool]:
    """Return ``(content, truncated)``."""
    if len(value) <= limit:
        return value, False
    return value[:limit], True
