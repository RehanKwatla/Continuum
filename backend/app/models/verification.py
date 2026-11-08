"""Verification model — the Verifier agent's verdict for one claim."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import VerificationVerdict
from app.models.types import CreatedAt, JsonArray, UuidFK, UuidPK, sa_enum


class Verification(Base):
    __tablename__ = "verifications"
    __table_args__ = (Index("ix_verifications_claim_created", "claim_id", "created_at"),)

    id: Mapped[UuidPK]
    claim_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    verdict: Mapped[VerificationVerdict] = mapped_column(
        sa_enum(VerificationVerdict, "verification_verdict", length=16), nullable=False
    )
    supporting_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True only when the quotation was found verbatim in the cited source text.
    quote_validated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Evidence span ids that contradict this claim (validated server-side).
    contradicted_by: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[CreatedAt]

    claim: Mapped["Claim"] = relationship(back_populates="verifications")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Verification claim={self.claim_id} {self.verdict}>"
