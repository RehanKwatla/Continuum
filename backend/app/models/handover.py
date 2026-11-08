"""Handover document model — a generated, claim-linked handover.

Only *approved* (Verified) claims may be referenced. ``claim_ids`` records the
exact set of approved claim ids used, and ``validation_errors`` records any
sentence the deterministic output validator rejected.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import HandoverStatus
from app.models.types import CreatedAt, JsonArray, JsonObject, UuidFK, UuidPK, sa_enum, UpdatedAt


class HandoverDocument(Base):
    __tablename__ = "handover_documents"
    __table_args__ = (Index("ix_handover_documents_project_created", "project_id", "created_at"),)

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    generated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[HandoverStatus] = mapped_column(
        sa_enum(HandoverStatus, "handover_status", length=16),
        nullable=False,
        default=HandoverStatus.GENERATED,
        server_default=HandoverStatus.GENERATED.value,
        index=True,
    )
    # Structured sections: [{key, title, statements: [{text, claim_ids: [...]}]}]
    sections: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    # Approved claim ids referenced anywhere in the document.
    claim_ids: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    # Sentences rejected by the deterministic validator (no approved claim link).
    validation_errors: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meta: Mapped[JsonObject] = mapped_column("metadata", nullable=False, default=dict)

    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HandoverDocument {self.id} {self.status}>"
