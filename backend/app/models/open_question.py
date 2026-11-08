"""Open question model — knowledge the sources do not answer.

Open questions are raised by the Extractor when evidence is insufficient, or by
the validators when a claim could not be supported. They stay in the uncertainty
centre until a human resolves them.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AccessLabel, OpenQuestionStatus
from app.models.types import CreatedAt, UuidFK, UuidPK, sa_enum


class OpenQuestion(Base):
    __tablename__ = "open_questions"
    __table_args__ = (
        Index("ix_open_questions_project_status", "project_id", "status"),
        Index("ix_open_questions_project_entity", "project_id", "entity"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The originating claim when the question came from an unsupported claim.
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("claims.id", ondelete="SET NULL"), nullable=True, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Deterministic key so reprocessing does not raise the same question twice.
    dedup_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[OpenQuestionStatus] = mapped_column(
        sa_enum(OpenQuestionStatus, "open_question_status", length=16),
        nullable=False,
        default=OpenQuestionStatus.OPEN,
        server_default=OpenQuestionStatus.OPEN.value,
        index=True,
    )
    access_label: Mapped[AccessLabel] = mapped_column(
        sa_enum(AccessLabel, "access_label", length=16),
        nullable=False,
        default=AccessLabel.WORKSPACE,
        server_default=AccessLabel.WORKSPACE.value,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[CreatedAt]

    claim: Mapped["Claim | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OpenQuestion {self.id} {self.status}>"
