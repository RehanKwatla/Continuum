"""Project schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProjectStatus
from app.schemas.workspace import WorkspaceSummary


class ProjectCreate(BaseModel):
    workspace_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    departing_role: str | None = Field(default=None, max_length=120)
    successor_role: str | None = Field(default=None, max_length=120)
    status: ProjectStatus = ProjectStatus.ACTIVE


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    departing_role: str | None = Field(default=None, max_length=120)
    successor_role: str | None = Field(default=None, max_length=120)
    status: ProjectStatus | None = None


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    full_name: str
    external_id: str | None = None
    description: str | None = None
    default_branch: str | None = None
    is_private: bool = False
    html_url: str | None = None
    connected_at: datetime
    metadata: dict = Field(
        default_factory=dict,
        validation_alias="meta",
        serialization_alias="metadata",
    )


class ProjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    status: ProjectStatus
    departing_role: str | None = None
    successor_role: str | None = None
    created_at: datetime
    updated_at: datetime
    source_count: int = 0
    repository_count: int = 0


class ProjectRead(ProjectSummary):
    workspace: WorkspaceSummary | None = None
    repositories: list[RepositoryRead] = Field(default_factory=list)
    source_type_counts: dict[str, int] = Field(default_factory=dict)
    processing_status_counts: dict[str, int] = Field(default_factory=dict)
