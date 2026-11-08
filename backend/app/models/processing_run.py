"""Processing run model — one execution of the reconstruction workflow.

A run records what the Phase 3 LangGraph workflow did, how far it got and what
failed. Failures are isolated per source so a single bad source never invalidates
the whole run (hence the ``PARTIAL`` status).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ProcessingRunStatus
from app.models.types import CreatedAt, JsonArray, JsonObject, UuidFK, UuidPK, sa_enum


class ProcessingRun(Base):
    __tablename__ = "processing_runs"
    __table_args__ = (
        Index("ix_processing_runs_project_created", "project_id", "created_at"),
        Index("ix_processing_runs_project_status", "project_id", "status"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[ProcessingRunStatus] = mapped_column(
        sa_enum(ProcessingRunStatus, "processing_run_status", length=16),
        nullable=False,
        default=ProcessingRunStatus.PENDING,
        server_default=ProcessingRunStatus.PENDING.value,
        index=True,
    )
    # Number of sources that passed the access filter and entered the workflow.
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verified_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uncertain_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Per-source failures/warnings; the run survives individual source errors.
    errors: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    stats: Mapped[JsonObject] = mapped_column(nullable=False, default=dict)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[CreatedAt]

    claims: Mapped[list["Claim"]] = relationship(back_populates="run")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ProcessingRun {self.id} {self.status}>"
