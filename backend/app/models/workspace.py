"""Workspace and workspace membership models."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import WorkspaceRole
from app.models.types import CreatedAt, UuidFK, UuidPK, sa_enum


def _role_enum() -> "SAEnum":
    return sa_enum(WorkspaceRole, "workspace_role", length=16)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[UuidPK]
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[CreatedAt]

    owner: Mapped["User"] = relationship(back_populates="owned_workspaces")  # noqa: F821
    members: Mapped[list["WorkspaceMember"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(  # noqa: F821
        back_populates="workspace", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Workspace {self.id} {self.name!r}>"


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
    )

    id: Mapped[UuidPK]
    workspace_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[WorkspaceRole] = mapped_column(_role_enum(), nullable=False)
    created_at: Mapped[CreatedAt]

    workspace: Mapped["Workspace"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<WorkspaceMember ws={self.workspace_id} user={self.user_id} role={self.role}>"
