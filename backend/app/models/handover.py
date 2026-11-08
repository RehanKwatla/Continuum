"""Handover document model — a generated, claim-linked handover.

Only *approved* (Verified) claims may be referenced. ``claim_ids`` records the
exact set of approved claim ids used, and ``validation_errors`` records any
sentence the deterministic output validator rejected.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
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
from app.models.enums import HandoverLifecycleStatus, HandoverStatus
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


class Handover(Base):
    """The logical handover for a project; its content lives in versions.

    Nothing here ever overwrites history: every significant edit appends a new
    :class:`HandoverVersion`, and a published version is immutable.
    """

    __tablename__ = "handovers"
    __table_args__ = (Index("ix_handovers_project_created", "project_id", "created_at"),)

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[HandoverLifecycleStatus] = mapped_column(
        sa_enum(HandoverLifecycleStatus, "handover_lifecycle_status", length=16),
        nullable=False,
        default=HandoverLifecycleStatus.DRAFT,
        server_default=HandoverLifecycleStatus.DRAFT.value,
        index=True,
    )
    #: Highest ``HandoverVersion.version_number`` written so far (0 = none).
    current_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    versions: Mapped[list["HandoverVersion"]] = relationship(
        back_populates="handover",
        cascade="all, delete-orphan",
        order_by="HandoverVersion.version_number.desc()",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Handover {self.id} v{self.current_version} {self.status}>"


class HandoverVersion(Base):
    """One immutable, reviewable version of a handover's content."""

    __tablename__ = "handover_versions"
    __table_args__ = (
        UniqueConstraint(
            "handover_id", "version_number", name="uq_handover_versions_handover_version"
        ),
        Index("ix_handover_versions_handover_created", "handover_id", "created_at"),
    )

    id: Mapped[UuidPK]
    handover_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("handovers.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The generated document this version was seeded from (never mutated).
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("handover_documents.id", ondelete="SET NULL"), nullable=True
    )
    #: Structured content: [{key, title, statements: [{statement_id, text,
    #: statement_type, claim_ids, claim_revisions, original_text, unsupported}]}]
    structured_content: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    #: Every approved claim id referenced anywhere in this version.
    included_claim_ids: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    #: {claim_id: revision_number} snapshot so a later edit invalidates the link.
    claim_revisions: Mapped[JsonObject] = mapped_column(
        "claim_revisions", nullable=False, default=dict
    )
    #: Statements the deterministic validator rejected, with explanations.
    validation_errors: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    #: Reviewer-authored notes (never presented as project facts).
    reviewer_notes: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    status: Mapped[HandoverLifecycleStatus] = mapped_column(
        sa_enum(HandoverLifecycleStatus, "handover_lifecycle_status", length=16),
        nullable=False,
        default=HandoverLifecycleStatus.DRAFT,
        server_default=HandoverLifecycleStatus.DRAFT.value,
        index=True,
    )
    generated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meta: Mapped[JsonObject] = mapped_column("metadata", nullable=False, default=dict)
    created_at: Mapped[CreatedAt]

    handover: Mapped["Handover"] = relationship(back_populates="versions")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HandoverVersion {self.id} v{self.version_number} {self.status}>"
