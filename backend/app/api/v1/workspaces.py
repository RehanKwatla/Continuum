"""Workspace endpoints (creation, listing, detail).

Every handler re-derives permission from the database; the client can never
read a workspace it is not a member of.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.dependencies import (
    CurrentUser,
    DbSession,
    resolve_workspace_access,
)
from app.models.enums import WorkspaceRole
from app.schemas.workspace import WorkspaceCreate, WorkspaceRead, WorkspaceSummary
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post(
    "",
    response_model=WorkspaceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace (the caller becomes its owner)",
)
def create_workspace(
    payload: WorkspaceCreate, user: CurrentUser, db: DbSession
) -> WorkspaceRead:
    return WorkspaceService(db).create(user, payload)


@router.get("", response_model=list[WorkspaceSummary], summary="List my workspaces")
def list_workspaces(user: CurrentUser, db: DbSession) -> list[WorkspaceSummary]:
    return WorkspaceService(db).list_for_user(user)


@router.get("/{workspace_id}", response_model=WorkspaceRead, summary="Get a workspace")
def get_workspace(
    workspace_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> WorkspaceRead:
    workspace, role = resolve_workspace_access(
        db, workspace_id=workspace_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    return WorkspaceService(db).to_read(workspace, role=role)
