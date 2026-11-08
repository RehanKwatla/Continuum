"""Evidence span model — a traceable, quotable region of a source.

The backend (never the LLM) creates these. Every span carries an exact
``start_offset``/``end_offset`` into the persisted source content so that any
supporting quotation can be validated byte-for-byte against the original.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.types import CreatedAt, JsonObject, UuidFK, UuidPK


class EvidenceSpan(Base):
    __tablename__ = "evidence_spans"
    __table_args__ = (
        UniqueConstraint("source_id", "span_index", name="uq_evidence_spans_source_index"),
        Index("ix_evidence_spans_source", "source_id"),
    )

    id: Mapped[UuidPK]
    source_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    span_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Human-readable locator, e.g. "README.md#L12-L18", "page 3", "commit abc123".
    location: Mapped[str] = mapped_column(String(500), nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured locator details: page_number, heading, line_start, line_end,
    # commit_sha, file_path, issue_number, pull_request_number, comment_id...
    meta: Mapped[JsonObject] = mapped_column("metadata", nullable=False, default=dict)

    created_at: Mapped[CreatedAt]

    source: Mapped["Source"] = relationship(back_populates="spans")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EvidenceSpan {self.id} source={self.source_id} #{self.span_index}>"
