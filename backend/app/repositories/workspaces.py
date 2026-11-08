"""Workspace data access."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.enums import WorkspaceRole
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.repositories.base import BaseRepository


class WorkspacesRepository(BaseRepository[Workspace]):
    model = Workspace

    def create(self, *, name: str, owner_id: uuid.UUID) -> Workspace:
        workspace = Workspace(name=name.strip(), owner_id=owner_id)
        self.db.add(workspace)
        return workspace

    def add_member(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, role: WorkspaceRole
    ) -> WorkspaceMember:
        membership = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
        self.db.add(membership)
        return membership

    def get_membership(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceMember | None:
        return self.db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        ).scalar_one_or_none()

    def list_for_user(self, user_id: uuid.UUID) -> list[tuple[Workspace, WorkspaceRole]]:
        rows = self.db.execute(
            select(Workspace, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.created_at.desc())
        ).all()
        return [(row[0], row[1]) for row in rows]

    def list_members(self, workspace_id: uuid.UUID) -> list[tuple[WorkspaceMember, User]]:
        rows = self.db.execute(
            select(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.created_at.asc())
        ).all()
        return [(row[0], row[1]) for row in rows]

    def project_count(self, workspace_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count())
                .select_from(Project)
                .where(Project.workspace_id == workspace_id)
            ).scalar_one()
        )

    def member_count(self, workspace_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count())
                .select_from(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == workspace_id)
            ).scalar_one()
        )
