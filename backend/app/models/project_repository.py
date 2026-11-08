"""Repository connected to a project (Phase 2: GitHub only)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.types import JsonObject, UuidFK, UuidPK


class ProjectRepository(Base):
    __tablename__ = "project_repositories"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "provider", "full_name", name="uq_project_repositories_project_provider_name"
        ),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="github")
    full_name: Mapped[str] = mapped_column(String(300), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_private: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    html_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    meta: Mapped[JsonObject] = mapped_column("metadata", nullable=False, default=dict)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="repositories")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ProjectRepository {self.full_name}>"
