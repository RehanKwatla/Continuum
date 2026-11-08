"""Project endpoints (CRUD + listing) and workspace-scoped isolation."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.core.dependencies import (
    CurrentUser,
    DbSession,
    resolve_project_access,
    resolve_workspace_access,
)
from app.models.enums import ProjectStatus, WorkspaceRole
from app.schemas.common import Page, build_page_meta
from app.schemas.project import ProjectCreate, ProjectRead, ProjectSummary, ProjectUpdate
from app.schemas.source import SourceDeleteResponse  # noqa: F401  (re-export for docs)
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project inside a workspace",
)
def create_project(
    payload: ProjectCreate, user: CurrentUser, db: DbSession
) -> ProjectRead:
    # Authorises against the *target* workspace before anything is written.
    _, role = resolve_workspace_access(
        db, workspace_id=payload.workspace_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    return ProjectService(db).create(user, payload, role=role)


@router.get("", response_model=Page[ProjectSummary], summary="List accessible projects")
def list_projects(
    user: CurrentUser,
    db: DbSession,
    workspace_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    project_status: ProjectStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[ProjectSummary]:
    if workspace_id is not None:
        # Never list a workspace the caller cannot access.
        resolve_workspace_access(
            db, workspace_id=workspace_id, user=user, required_role=WorkspaceRole.VIEWER
        )

    items, total = ProjectService(db).list(
        user,
        workspace_id=workspace_id,
        search=search,
        status=project_status,
        page=page,
        page_size=page_size,
    )
    return Page[ProjectSummary](items=items, meta=build_page_meta(total, page, page_size))


@router.get("/{project_id}", response_model=ProjectRead, summary="Get a project")
def get_project(project_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ProjectRead:
    project, role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    return ProjectService(db).to_read(project, role=role)


@router.patch("/{project_id}", response_model=ProjectRead, summary="Update a project")
def update_project(
    project_id: uuid.UUID, payload: ProjectUpdate, user: CurrentUser, db: DbSession
) -> ProjectRead:
    project, role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    return ProjectService(db).update(project, payload, user=user, role=role)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project (admins only)",
)
def delete_project(project_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    project, _ = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.ADMIN
    )
    ProjectService(db).delete(project, user=user)
