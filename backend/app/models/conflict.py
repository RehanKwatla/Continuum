"""Conflict models — contradictions detected between two or more claims.

Conflict *detection* is deterministic application code (see
``app.services.conflict_detector``); the LLM is never asked to decide whether
two statements contradict one another. A human reviewer resolves conflicts and
the resolution is preserved on the record.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ClaimType, ConflictStatus
from app.models.types import CreatedAt, JsonObject, UuidFK, UuidPK, sa_enum


class Conflict(Base):
    __tablename__ = "conflicts"
    __table_args__ = (
        Index("ix_conflicts_project_status", "project_id", "status"),
        Index("ix_conflicts_project_property", "project_id", "property_key"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    entity: Mapped[str | None] = mapped_column(String(300), nullable=True)
    claim_type: Mapped[ClaimType | None] = mapped_column(
        sa_enum(ClaimType, "claim_type", length=32), nullable=True
    )
    # Deterministic grouping key, e.g. "postgres_version" or "payments owner".
    property_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # "value_disagreement" | "changed_over_time" (informational, not a conflict)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="value_disagreement")
    status: Mapped[ConflictStatus] = mapped_column(
        sa_enum(ConflictStatus, "conflict_status", length=16),
        nullable=False,
        default=ConflictStatus.OPEN,
        server_default=ConflictStatus.OPEN.value,
        index=True,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Phase 4: which of the five resolution options the reviewer chose.
    #: Stored as its own column so the contradiction and its resolution are kept
    #: separately — the original claims and evidence are never deleted.
    resolution: Mapped[str | None] = mapped_column(String(48), nullable=True)
    resolution_meta: Mapped[JsonObject] = mapped_column(
        "resolution_metadata", nullable=False, default=dict
    )
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[CreatedAt]

    links: Mapped[list["ConflictClaim"]] = relationship(
        back_populates="conflict", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Conflict {self.id} {self.status} key={self.property_key}>"


class ConflictClaim(Base):
    """Association between a conflict and the claims that disagree."""

    __tablename__ = "conflict_claims"
    __table_args__ = (
        UniqueConstraint("conflict_id", "claim_id", name="uq_conflict_claims_conflict_claim"),
    )

    id: Mapped[UuidPK]
    conflict_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("conflicts.id", ondelete="CASCADE"), index=True
    )
    claim_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    relation: Mapped[str] = mapped_column(String(32), nullable=False, default="contradicts")

    conflict: Mapped["Conflict"] = relationship(back_populates="links")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConflictClaim conflict={self.conflict_id} claim={self.claim_id}>"
