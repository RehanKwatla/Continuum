"""File-system and archive-path helpers."""

from __future__ import annotations

import posixpath
import re
import uuid
from typing import BinaryIO

#: Extensions Continuum accepts for direct upload.
ALLOWED_UPLOAD_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".md", ".markdown", ".txt", ".zip"})

#: Extensions permitted *inside* a ZIP archive.
ALLOWED_ARCHIVE_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".md", ".markdown", ".txt", ".rst", ".adoc", ".csv", ".json", ".yaml", ".yml"}
)

#: Extensions we explicitly refuse to ingest.
DENIED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".lib", ".obj",
        ".msi", ".dmg", ".apk", ".ipa", ".iso", ".img", ".jar", ".class",
        ".pyc", ".pyo", ".wasm", ".com", ".bat", ".cmd", ".sh", ".ps1",
        ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
        ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".asc",
    }
)

#: Exact file names that must never be ingested.
DENIED_FILENAMES: frozenset[str] = frozenset(
    {
        ".env", ".env.local", ".env.production", ".env.development",
        ".npmrc", ".netrc", ".git-credentials", ".htpasswd", ".dockercfg",
        "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
        "credentials", "credentials.json", "secrets.yml", "secrets.yaml",
        "secrets.json", "terraform.tfstate", ".pgpass", "shadow",
    }
)

#: Path fragments that disqualify an archive member.
DENIED_PATH_PARTS: frozenset[str] = frozenset(
    {
        ".git", "node_modules", "__pycache__", ".venv", "venv", ".tox",
        ".mypy_cache", ".pytest_cache", ".idea", ".vscode", "dist", "build",
        ".next", "vendor", "target", ".terraform", ".ssh", ".aws", ".gnupg",
    }
)

_INVALID_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_MAGIC_PDF = b"%PDF-"
_MAGIC_ZIP = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def sanitize_filename(name: str) -> str:
    """Reduce an arbitrary client-supplied name to a safe basename."""
    candidate = (name or "").replace("\\", "/")
    candidate = posixpath.basename(candidate)
    candidate = _INVALID_FILENAME_CHARS.sub("_", candidate).strip("._-")
    return candidate[:200] or "unnamed"


def extension_of(name: str) -> str:
    candidate = sanitize_filename(name).lower()
    dot = candidate.rfind(".")
    if dot <= 0:
        return ""
    return candidate[dot:]


def detect_actual_format(head: bytes, filename: str) -> str:
    """Return one of ``pdf`` | ``zip`` | ``markdown`` | ``text`` | ``unknown``."""
    if head.startswith(_MAGIC_PDF):
        return "pdf"
    if any(head.startswith(magic) for magic in _MAGIC_ZIP):
        return "zip"

    ext = extension_of(filename)
    if ext in {".md", ".markdown"}:
        return "markdown"
    if ext in {".txt", ".rst", ".adoc", ".csv", ".json", ".yaml", ".yml"}:
        return "text"

    if b"\x00" not in head[:4096]:
        try:
            head[:4096].decode("utf-8")
            return "text"
        except UnicodeDecodeError:
            return "unknown"
    return "unknown"


def normalize_archive_path(path: str) -> str | None:
    """Return a safe relative POSIX path, or ``None`` for hostile entries.

    Blocks zip-slip / path traversal, absolute paths, drive letters and
    backslash escapes.
    """
    if not path:
        return None
    candidate = path.replace("\\", "/")
    if candidate.startswith("/") or re.match(r"^[A-Za-z]:", candidate):
        return None
    # Preserve a single trailing slash marker to detect directory entries.
    candidate = posixpath.normpath(candidate)
    if candidate in {".", ".."} or candidate.startswith("../") or "/../" in candidate:
        return None
    if candidate.startswith("/"):
        return None
    return candidate


def is_denied_filename(name: str) -> bool:
    return sanitize_filename(name).lower() in DENIED_FILENAMES


def is_denied_path(path: str) -> bool:
    parts = {part.lower() for part in path.split("/")}
    return bool(parts & DENIED_PATH_PARTS)


def read_limited(stream: BinaryIO, max_bytes: int, chunk_size: int = 1024 * 1024) -> bytes:
    """Read at most ``max_bytes + 1`` bytes so callers can detect oversize input."""
    chunks: list[bytes] = []
    remaining = max_bytes + 1
    while remaining > 0:
        chunk = stream.read(min(chunk_size, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def safe_storage_key(filename: str) -> str:
    ext = extension_of(filename) or ".bin"
    return f"{uuid.uuid4().hex}{ext}"


def human_size(num_bytes: int | None) -> str:
    if num_bytes is None:
        return "unknown"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
