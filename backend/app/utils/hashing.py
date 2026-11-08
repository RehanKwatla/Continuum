"""Content hashing helpers used for de-duplication."""

from __future__ import annotations

import hashlib


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8", errors="replace"))


def compute_content_hash(source_type: str, external_id: str | None, content: str | None) -> str:
    """Deterministic hash over the identity + normalised content of a source.

    ``storage_key`` is deliberately excluded so re-uploading the same file is
    detected as a duplicate.
    """
    payload = "\x1f".join(
        [
            str(source_type),
            external_id or "",
            (content or "").strip(),
        ]
    )
    return sha256_text(payload)
