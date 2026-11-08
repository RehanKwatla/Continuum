"""Source model — the normalised unit of ingested knowledge."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AccessLabel, FreshnessStatus, ProcessingStatus, SourceType
from app.models.types import CreatedAt, JsonArray, JsonObject, UuidFK, UuidPK, sa_enum


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        Index("ix_sources_project_type", "project_id", "source_type"),
        Index("ix_sources_project_status", "project_id", "processing_status"),
        UniqueConstraint("project_id", "content_hash", name="uq_sources_project_content_hash"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[SourceType] = mapped_column(
        sa_enum(SourceType, "source_type", length=32), nullable=False, index=True
    )
    source_name: Mapped[str] = mapped_column(String(500), nullable=False)
    # Identifier inside the origin system (commit SHA, issue number, file path...).
    external_id: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NOTE: attribute is `meta` because `metadata` is reserved by SQLAlchemy.
    meta: Mapped[JsonObject] = mapped_column("metadata", nullable=False, default=dict)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    access_label: Mapped[AccessLabel] = mapped_column(
        sa_enum(AccessLabel, "access_label", length=16),
        nullable=False,
        default=AccessLabel.WORKSPACE,
        server_default=AccessLabel.WORKSPACE.value,
    )
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        sa_enum(ProcessingStatus, "processing_status", length=16),
        nullable=False,
        default=ProcessingStatus.PENDING,
        server_default=ProcessingStatus.PENDING.value,
        index=True,
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # --- Phase 3 freshness ---------------------------------------------------
    # Deterministic staleness assessment; a *potentially stale* source is
    # flagged for review rather than silently replaced by newer information.
    freshness: Mapped[FreshnessStatus] = mapped_column(
        sa_enum(FreshnessStatus, "source_freshness", length=32),
        nullable=False,
        default=FreshnessStatus.CURRENT,
        server_default=FreshnessStatus.CURRENT.value,
        index=True,
    )
    freshness_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Ingestion bookkeeping ----------------------------------------------
    storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[JsonArray] = mapped_column(nullable=False, default=list)

    created_at: Mapped[CreatedAt]

    project: Mapped["Project"] = relationship(back_populates="sources")  # noqa: F821
    evidence: Mapped[list["Evidence"]] = relationship(  # noqa: F821
        back_populates="source", cascade="all, delete-orphan"
    )
    spans: Mapped[list["EvidenceSpan"]] = relationship(  # noqa: F821
        back_populates="source", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Source {self.id} {self.source_type} {self.source_name!r}>"
