"""Dashboard aggregate schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ProcessingStatus, SourceType
from app.schemas.project import ProjectSummary


class RecentSourceItem(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    source_type: SourceType
    source_name: str
    processing_status: ProcessingStatus
    created_at: datetime


class DashboardStats(BaseModel):
    """Real aggregates computed from the database — never mocked."""

    total_projects: int = 0
    total_sources: int = 0
    total_workspaces: int = 0
    total_connected_repositories: int = 0
    source_type_counts: dict[str, int] = Field(default_factory=dict)
    processing_status_counts: dict[str, int] = Field(default_factory=dict)
    recent_projects: list[ProjectSummary] = Field(default_factory=list)
    recent_sources: list[RecentSourceItem] = Field(default_factory=list)
    upcoming: list[str] = Field(
        default_factory=lambda: [
            "Claim extraction (Phase 3)",
            "Evidence verification (Phase 3)",
            "Handover generation (Phase 3)",
        ]
    )
