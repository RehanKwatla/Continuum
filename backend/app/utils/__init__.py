"""Utility helpers."""

from app.utils.files import (
    ALLOWED_UPLOAD_EXTENSIONS,
    detect_actual_format,
    extension_of,
    human_size,
    normalize_archive_path,
    read_limited,
    safe_storage_key,
    sanitize_filename,
)
from app.utils.hashing import compute_content_hash, sha256_bytes, sha256_text
from app.utils.text import (
    collapse_blank_lines,
    normalize_newlines,
    normalize_text,
    strip_control_characters,
    truncate_content,
)

__all__ = [
    "ALLOWED_UPLOAD_EXTENSIONS",
    "collapse_blank_lines",
    "compute_content_hash",
    "detect_actual_format",
    "extension_of",
    "human_size",
    "normalize_archive_path",
    "normalize_newlines",
    "normalize_text",
    "read_limited",
    "safe_storage_key",
    "sanitize_filename",
    "sha256_bytes",
    "sha256_text",
    "strip_control_characters",
    "truncate_content",
]
