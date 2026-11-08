"""Source ingestion and retrieval schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AccessLabel, ProcessingStatus, SourceType
from app.schemas.common import PageMeta


class SourceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    source_type: SourceType
    source_name: str
    external_id: str | None = None
    author: str | None = None
    created_at_source: datetime | None = None
    access_label: AccessLabel
    processing_status: ProcessingStatus
    content_hash: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    source_url: str | None = None
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata: dict = Field(
        default_factory=dict,
        validation_alias="meta",
        serialization_alias="metadata",
    )
    content_preview: str | None = Field(
        default=None, description="First ~400 characters of the normalised content."
    )


class SourceRead(SourceSummary):
    content: str | None = None


class SourceListResponse(BaseModel):
    items: list[SourceSummary]
    meta: PageMeta
    type_counts: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)


class IngestionResult(BaseModel):
    """Outcome for a single ingested artefact (upload entry or GitHub record)."""

    filename: str
    source_id: uuid.UUID | None = None
    source_type: SourceType | None = None
    status: ProcessingStatus
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    duplicate_of: uuid.UUID | None = None


class UploadResponse(BaseModel):
    results: list[IngestionResult]
    accepted: int
    duplicates: int
    failed: int


class SourceDeleteResponse(BaseModel):
    id: uuid.UUID
    deleted: bool = True
