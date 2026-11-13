"""Snapshot-scoped evidence derived from Git commit history."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.types import CreatedAt, JsonArray, JsonObject, UuidFK, UuidPK


class HistoryAnalysisRun(Base):
    __tablename__ = "history_analysis_runs"
    __table_args__ = (UniqueConstraint("snapshot_id", "analysis_version", name="uq_history_analysis_snapshot_version"),)

    id: Mapped[UuidPK]
    snapshot_id: Mapped[UuidFK] = mapped_column(ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True)
    analysis_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="completed", server_default="completed")
    coverage: Mapped[JsonObject]
    contributors: Mapped[JsonArray]
    hotspots: Mapped[JsonArray]
    co_changes: Mapped[JsonArray]
    summary: Mapped[JsonObject]
    created_at: Mapped[CreatedAt]


class CommitFileChange(Base):
    __tablename__ = "commit_file_changes"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "commit_sha", "file_path", name="uq_commit_file_changes_snapshot_sha_path"),
        Index("ix_commit_file_changes_snapshot_path", "snapshot_id", "file_path"),
    )

    id: Mapped[UuidPK]
    snapshot_id: Mapped[UuidFK] = mapped_column(ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    previous_filename: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    additions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deletions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    changes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    statistics_available: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    patch_available: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    created_at: Mapped[CreatedAt]


class CommitInsight(Base):
    __tablename__ = "commit_insights"
    __table_args__ = (UniqueConstraint("snapshot_id", "commit_sha", "analysis_version", name="uq_commit_insight_snapshot_sha_version"),)

    id: Mapped[UuidPK]
    snapshot_id: Mapped[UuidFK] = mapped_column(ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    analysis_version: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    classification_method: Mapped[str] = mapped_column(String(64), nullable=False, default="deterministic_signals", server_default="deterministic_signals")
    signals: Mapped[JsonArray]
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    affected_components: Mapped[JsonArray]
    source_references: Mapped[JsonArray]
    created_at: Mapped[CreatedAt]
