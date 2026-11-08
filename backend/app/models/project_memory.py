"""Project memory model — the per-project aggregate of reconstructed knowledge.

One row per project (reprocessing updates it rather than inserting duplicates).
It stores the derived counts and a short generated summary so the memory
overview can be rendered without re-aggregating every claim.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.types import CreatedAt, JsonObject, UuidFK, UuidPK


class ProjectMemory(Base):
    __tablename__ = "project_memory"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_project_memory_project"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Bumped each time the memory is rebuilt.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Category → count, status → count, plus freshness/conflict aggregates.
    stats: Mapped[JsonObject] = mapped_column(nullable=False, default=dict)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[CreatedAt]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ProjectMemory project={self.project_id} v{self.version}>"
