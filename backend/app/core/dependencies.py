"""FastAPI security dependencies: identity and resource authorisation."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, NotFoundError
from app.core.permissions import has_at_least, role_rank
from app.core.security import AuthPrincipal, extract_bearer_token, principal_from_token
from app.db.session import get_db
from app.models.enums import WorkspaceRole
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Workspace
from app.repositories.projects import ProjectsRepository
from app.repositories.workspaces import WorkspacesRepository
from app.services.auth_service import AuthService

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_current_principal(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> AuthPrincipal:
    return principal_from_token(extract_bearer_token(authorization))


CurrentPrincipal = Annotated[AuthPrincipal, Depends(get_current_principal)]


def get_current_user(principal: CurrentPrincipal, db: DbSession) -> User:
    """Resolve (and on first sight provision) the local user record."""
    return AuthService(db).resolve_user(principal)


CurrentUser = Annotated[User, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Plain helpers (also callable directly from services)
# ---------------------------------------------------------------------------
def resolve_workspace_access(
    db: Session, *, workspace_id: uuid.UUID, user: User, required_role: WorkspaceRole
) -> tuple[Workspace, WorkspaceRole]:
    """Return ``(workspace, role)`` or raise 404/403.

    Workspaces the user is not a member of are reported as *not found* so the
    API never leaks the existence of another tenant's resources.
    """
    workspaces = WorkspacesRepository(db)
    workspace = workspaces.get(workspace_id)
    if workspace is None:
        raise NotFoundError("Workspace not found.")

    membership = workspaces.get_membership(workspace_id=workspace_id, user_id=user.id)
    if membership is None:
        raise NotFoundError("Workspace not found.")

    if not has_at_least(membership.role, required_role):
        raise ForbiddenError(
            f"This action requires the '{required_role.value}' role or higher in this workspace.",
            details={"your_role": membership.role.value, "required_role": required_role.value},
        )
    return workspace, membership.role


def resolve_project_access(
    db: Session, *, project_id: uuid.UUID, user: User, required_role: WorkspaceRole
) -> tuple[Project, WorkspaceRole]:
    """Return ``(project, role)`` after enforcing workspace isolation."""
    project = ProjectsRepository(db).get(project_id)
    if project is None:
        raise NotFoundError("Project not found.")

    membership = WorkspacesRepository(db).get_membership(
        workspace_id=project.workspace_id, user_id=user.id
    )
    if membership is None:
        # Do not reveal that the project exists in another workspace.
        raise NotFoundError("Project not found.")

    if not has_at_least(membership.role, required_role):
        raise ForbiddenError(
            f"This action requires the '{required_role.value}' role or higher in this workspace.",
            details={"your_role": membership.role.value, "required_role": required_role.value},
        )
    return project, membership.role


# ---------------------------------------------------------------------------
# Dependency factories for routers
# ---------------------------------------------------------------------------
def project_reader() -> object:
    def dependency(
        project_id: uuid.UUID,
        user: CurrentUser,
        db: DbSession,
    ) -> Project:
        project, _ = resolve_project_access(
            db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
        )
        return project

    return Depends(dependency)


def project_writer() -> object:
    def dependency(
        project_id: uuid.UUID,
        user: CurrentUser,
        db: DbSession,
    ) -> Project:
        project, _ = resolve_project_access(
            db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
        )
        return project

    return Depends(dependency)


def project_admin() -> object:
    def dependency(
        project_id: uuid.UUID,
        user: CurrentUser,
        db: DbSession,
    ) -> Project:
        project, _ = resolve_project_access(
            db, project_id=project_id, user=user, required_role=WorkspaceRole.ADMIN
        )
        return project

    return Depends(dependency)


def workspace_member() -> object:
    def dependency(
        workspace_id: uuid.UUID,
        user: CurrentUser,
        db: DbSession,
    ) -> Workspace:
        workspace, _ = resolve_workspace_access(
            db, workspace_id=workspace_id, user=user, required_role=WorkspaceRole.MEMBER
        )
        return workspace

    return Depends(dependency)


def highest_role(roles: list[WorkspaceRole]) -> WorkspaceRole | None:
    if not roles:
        return None
    return max(roles, key=role_rank)
