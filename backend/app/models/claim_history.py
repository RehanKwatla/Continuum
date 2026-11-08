"""Claim history model — append-only audit trail for every claim.

Every status transition (Supported → Verified, open → resolved conflict, stale
flagging) is recorded so a reviewer can see who changed what, when and why.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ClaimStatus
from app.models.types import CreatedAt, JsonObject, UuidFK, UuidPK, sa_enum


class ClaimHistory(Base):
    __tablename__ = "claim_history"
    __table_args__ = (Index("ix_claim_history_claim_created", "claim_id", "created_at"),)

    id: Mapped[UuidPK]
    claim_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # e.g. "extracted" | "verified" | "reviewed" | "conflict_flagged" | "deduped"
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    from_status: Mapped[ClaimStatus | None] = mapped_column(
        sa_enum(ClaimStatus, "claim_status", length=16), nullable=True
    )
    to_status: Mapped[ClaimStatus | None] = mapped_column(
        sa_enum(ClaimStatus, "claim_status", length=16), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[JsonObject] = mapped_column("metadata", nullable=False, default=dict)

    created_at: Mapped[CreatedAt]

    claim: Mapped["Claim"] = relationship(back_populates="history")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ClaimHistory {self.action} claim={self.claim_id}>"
