"""Claim revision + reviewer-decision models (Phase 4).

A claim's text can be corrected by a reviewer, but an edit must never silently
inherit the previous evidence verification. Every edit therefore:

* preserves the previous revision as an immutable row;
* stores the edited text as a **new** revision;
* marks the new revision as requiring verification, and
* forces a fresh human approval before the claim can re-enter a handover.

:class:`ClaimDecision` records the human decision itself, including which
revision the reviewer approved. Only an *approved* decision on the *current*
revision can put a claim into a handover.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ClaimType, ReviewDecision
from app.models.types import CreatedAt, JsonObject, UuidFK, UuidPK, sa_enum


class ClaimRevision(Base):
    """One immutable revision of a claim's statement."""

    __tablename__ = "claim_revisions"
    __table_args__ = (
        UniqueConstraint(
            "claim_id", "revision_number", name="uq_claim_revisions_claim_revision"
        ),
        Index("ix_claim_revisions_claim_created", "claim_id", "created_at"),
    )

    id: Mapped[UuidPK]
    claim_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[ClaimType] = mapped_column(
        sa_enum(ClaimType, "claim_type", length=32), nullable=False
    )
    entity: Mapped[str | None] = mapped_column(String(300), nullable=True)
    #: Why the reviewer changed the statement (required for edits).
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    #: True when the reviewer changed the statement rather than the metadata.
    is_material: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: A materially-edited revision must be verified again before approval.
    verification_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    verification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("verifications.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[CreatedAt]

    claim: Mapped["Claim"] = relationship(back_populates="revisions")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ClaimRevision claim={self.claim_id} v{self.revision_number}>"


class ClaimDecision(Base):
    """An atomic, auditable human decision about one claim revision."""

    __tablename__ = "claim_decisions"
    __table_args__ = (
        Index("ix_claim_decisions_claim_created", "claim_id", "created_at"),
        Index("ix_claim_decisions_project_decision", "project_id", "decision"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    claim_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    #: The exact revision the reviewer saw and decided on.
    claim_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("claim_revisions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    decision: Mapped[ReviewDecision] = mapped_column(
        sa_enum(ReviewDecision, "review_decision", length=32), nullable=False, index=True
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    meta: Mapped[JsonObject] = mapped_column("metadata", nullable=False, default=dict)
    created_at: Mapped[CreatedAt]

    claim: Mapped["Claim"] = relationship(back_populates="decisions")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ClaimDecision claim={self.claim_id} {self.decision}>"
