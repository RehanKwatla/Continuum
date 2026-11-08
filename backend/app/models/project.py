"""Project model."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ProjectStatus
from app.models.types import CreatedAt, UpdatedAt, UuidFK, UuidPK, sa_enum


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[UuidPK]
    workspace_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        sa_enum(ProjectStatus, "project_status", length=32),
        nullable=False,
        default=ProjectStatus.ACTIVE,
        server_default=ProjectStatus.ACTIVE.value,
        index=True,
    )
    # Roles involved in the knowledge handover.
    departing_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    successor_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    workspace: Mapped["Workspace"] = relationship(back_populates="projects")  # noqa: F821
    sources: Mapped[list["Source"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    repositories: Mapped[list["ProjectRepository"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Project {self.id} {self.name!r}>"
