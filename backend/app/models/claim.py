"""Claim model — a knowledge assertion awaiting evidence and human review."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ClaimStatus, ClaimType
from app.models.types import CreatedAt, UuidFK, UuidPK, sa_enum


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        Index("ix_claims_project_status", "project_id", "status"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
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
    created_at: Mapped[CreatedAt]

    evidence: Mapped[list["Evidence"]] = relationship(  # noqa: F821
        back_populates="claim", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Claim {self.id} {self.status}>"
