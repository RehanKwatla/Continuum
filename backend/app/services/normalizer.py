"""Normalisation engine.

Every source — GitHub record or uploaded file — is converted into one common
internal shape before it reaches the database or a future AI workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.models.enums import AccessLabel, SourceType
from app.utils.hashing import compute_content_hash

#: JSON shape documented in docs/SCHEMAS.md.
NORMALIZED_SOURCE_EXAMPLE: dict[str, Any] = {
    "id": "uuid",
    "project_id": "uuid",
    "source_type": "github_commit",
    "source_name": "commit message or filename",
    "content": "extracted text",
    "author": "author name",
    "created_at_source": "timestamp",
    "metadata": {},
    "access_label": "workspace",
    "content_hash": "sha256",
    "processing_status": "completed",
}


@dataclass
class NormalizedSource:
    """Canonical, provider-agnostic representation of one artefact."""

    source_type: SourceType
    source_name: str
    content: str
    external_id: str | None = None
    author: str | None = None
    created_at_source: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    access_label: AccessLabel = AccessLabel.WORKSPACE
    warnings: list[str] = field(default_factory=list)
    source_url: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    storage_key: str | None = None

    @property
    def content_hash(self) -> str:
        return compute_content_hash(self.source_type.value, self.external_id, self.content)

    def to_dict(self, *, source_id: str, project_id: str) -> dict[str, Any]:
        return {
            "id": source_id,
            "project_id": project_id,
            "source_type": self.source_type.value,
            "source_name": self.source_name,
            "content": self.content,
            "author": self.author,
            "created_at_source": (
                self.created_at_source.isoformat() if self.created_at_source else None
            ),
            "metadata": self.metadata,
            "access_label": self.access_label.value,
            "content_hash": self.content_hash,
            "processing_status": "completed",
        }


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_normalized_source(
    *,
    source_type: SourceType,
    source_name: str,
    content: str,
    external_id: str | None = None,
    author: str | None = None,
    created_at_source: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    access_label: AccessLabel = AccessLabel.WORKSPACE,
    warnings: list[str] | None = None,
    source_url: str | None = None,
    mime_type: str | None = None,
    size_bytes: int | None = None,
    storage_key: str | None = None,
) -> NormalizedSource:
    """Build a :class:`NormalizedSource`, normalising timestamps and metadata."""
    return NormalizedSource(
        source_type=source_type,
        source_name=(source_name or "untitled")[:500],
        content=content or "",
        external_id=external_id,
        author=author,
        created_at_source=ensure_utc(created_at_source),
        metadata=metadata or {},
        access_label=access_label,
        warnings=list(warnings or []),
        source_url=source_url,
        mime_type=mime_type,
        size_bytes=size_bytes,
        storage_key=storage_key,
    )
