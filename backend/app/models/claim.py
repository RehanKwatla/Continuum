"""Claim model — a knowledge assertion awaiting evidence and human review."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AccessLabel, ClaimStatus, ClaimType
from app.models.types import CreatedAt, UpdatedAt, UuidFK, UuidPK, sa_enum


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        Index("ix_claims_project_status", "project_id", "status"),
        Index("ix_claims_project_type", "project_id", "claim_type"),
        Index("ix_claims_project_entity", "project_id", "entity"),
        # Deterministic deduplication key (normalised text hash) per project.
        UniqueConstraint("project_id", "dedup_key", name="uq_claims_project_dedup_key"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[ClaimType] = mapped_column(
        sa_enum(ClaimType, "claim_type", length=32),
        nullable=False,
        default=ClaimType.OTHER,
        server_default=ClaimType.OTHER.value,
    )
    entity: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[ClaimStatus] = mapped_column(
        sa_enum(ClaimStatus, "claim_status", length=16),
        nullable=False,
        default=ClaimStatus.UNCERTAIN,
        server_default=ClaimStatus.UNCERTAIN.value,
        index=True,
    )
    critical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # --- Phase 3 provenance --------------------------------------------------
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_label: Mapped[AccessLabel] = mapped_column(
        sa_enum(AccessLabel, "access_label", length=16),
        nullable=False,
        default=AccessLabel.WORKSPACE,
        server_default=AccessLabel.WORKSPACE.value,
    )
    # Normalised-text hash used to avoid storing the same claim twice.
    dedup_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # --- Human review --------------------------------------------------------
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    evidence: Mapped[list["Evidence"]] = relationship(  # noqa: F821
        back_populates="claim", cascade="all, delete-orphan"
    )
    verifications: Mapped[list["Verification"]] = relationship(  # noqa: F821
        back_populates="claim", cascade="all, delete-orphan"
    )
    history: Mapped[list["ClaimHistory"]] = relationship(  # noqa: F821
        back_populates="claim", cascade="all, delete-orphan"
    )
    run: Mapped["ProcessingRun | None"] = relationship(back_populates="claims")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Claim {self.id} {self.status}>"
