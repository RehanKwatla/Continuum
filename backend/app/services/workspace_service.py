"""Workspace service: creation, listing and membership."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.enums import WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace
from app.repositories.workspaces import WorkspacesRepository
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberRead,
    WorkspaceRead,
    WorkspaceSummary,
)
from app.services import audit_service


class WorkspaceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.workspaces = WorkspacesRepository(db)

    def create(self, user: User, payload: WorkspaceCreate) -> WorkspaceRead:
        workspace = self.workspaces.create(name=payload.name, owner_id=user.id)
        self.workspaces.flush()
        self.workspaces.add_member(
            workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER
        )
        self.db.commit()
        self.db.refresh(workspace)

        audit_service.record(
            self.db,
            action="workspace.created",
            user_id=user.id,
            workspace_id=workspace.id,
            resource_type="workspace",
            resource_id=workspace.id,
            metadata={"name": workspace.name},
        )
        return self.to_read(workspace, role=WorkspaceRole.OWNER)

    def list_for_user(self, user: User) -> list[WorkspaceSummary]:
        rows = self.workspaces.list_for_user(user.id)
        return [
            self.to_summary(workspace, role=role)
            for workspace, role in rows
        ]

    def to_summary(self, workspace: Workspace, *, role: WorkspaceRole | None) -> WorkspaceSummary:
        return WorkspaceSummary(
            id=workspace.id,
            name=workspace.name,
            owner_id=workspace.owner_id,
            created_at=workspace.created_at,
            role=role,
            project_count=self.workspaces.project_count(workspace.id),
            member_count=self.workspaces.member_count(workspace.id),
        )

    def to_read(self, workspace: Workspace, *, role: WorkspaceRole | None) -> WorkspaceRead:
        summary = self.to_summary(workspace, role=role)
        members = [
            WorkspaceMemberRead(
                id=membership.id,
                user_id=membership.user_id,
                role=membership.role,
                created_at=membership.created_at,
                email=member_user.email,
                full_name=member_user.full_name,
            )
            for membership, member_user in self.workspaces.list_members(workspace.id)
        ]
        return WorkspaceRead(**summary.model_dump(), members=members)

    def workspace_ids_for_user(self, user: User) -> list[uuid.UUID]:
        return [workspace.id for workspace, _ in self.workspaces.list_for_user(user.id)]
