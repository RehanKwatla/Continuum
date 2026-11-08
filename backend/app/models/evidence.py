"""Evidence model — links a claim to the exact span of a source that supports it."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.types import CreatedAt, UuidFK, UuidPK


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_claim_source", "claim_id", "source_id"),
    )

    id: Mapped[UuidPK]
    claim_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    # Human-readable locator, e.g. "README.md#L12-L18" or "page 3".
    source_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supporting_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[CreatedAt]

    claim: Mapped["Claim"] = relationship(back_populates="evidence")  # noqa: F821
    source: Mapped["Source"] = relationship(back_populates="evidence")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Evidence claim={self.claim_id} source={self.source_id}>"
