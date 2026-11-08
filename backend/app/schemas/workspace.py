"""Workspace schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import WorkspaceRole


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="Human readable workspace name.")


class WorkspaceMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    role: WorkspaceRole
    created_at: datetime
    email: str | None = None
    full_name: str | None = None


class WorkspaceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    created_at: datetime
    role: WorkspaceRole | None = Field(
        default=None, description="Role of the requesting user in this workspace."
    )
    project_count: int = 0
    member_count: int = 0


class WorkspaceRead(WorkspaceSummary):
    members: list[WorkspaceMemberRead] = Field(default_factory=list)
