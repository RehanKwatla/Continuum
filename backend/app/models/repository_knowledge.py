"""Snapshot-scoped reconstructed project knowledge and its evidence graph."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.types import CreatedAt, JsonArray, JsonObject, UpdatedAt, UuidFK, UuidPK


class KnowledgeAnalysisRun(Base):
    __tablename__ = "knowledge_analysis_runs"
    __table_args__ = (UniqueConstraint("snapshot_id", "analysis_version", name="uq_knowledge_runs_snapshot_version"),)

    id: Mapped[UuidPK]
    snapshot_id: Mapped[UuidFK] = mapped_column(ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True)
    analysis_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", server_default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    coverage: Mapped[JsonObject]
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class KnowledgeUnit(Base):
    __tablename__ = "knowledge_units"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "dedup_key", name="uq_knowledge_units_run_dedup"),
        Index("ix_knowledge_units_run_category", "analysis_run_id", "category"),
        Index("ix_knowledge_units_run_level", "analysis_run_id", "evidence_level"),
    )

    id: Mapped[UuidPK]
    analysis_run_id: Mapped[UuidFK] = mapped_column(ForeignKey("knowledge_analysis_runs.id", ondelete="CASCADE"), index=True)
    repository_id: Mapped[UuidFK] = mapped_column(ForeignKey("repository_connections.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[UuidFK] = mapped_column(ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_level: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.7)
    extraction_method: Mapped[str] = mapped_column(String(64), nullable=False)
    extraction_version: Mapped[str] = mapped_column(String(32), nullable=False)
    freshness_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unverified")
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class KnowledgeEvidence(Base):
    __tablename__ = "knowledge_evidence"
    __table_args__ = (Index("ix_knowledge_evidence_unit", "knowledge_unit_id"),)

    id: Mapped[UuidPK]
    knowledge_unit_id: Mapped[UuidFK] = mapped_column(ForeignKey("knowledge_units.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[UuidFK] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    evidence_span_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_spans.id", ondelete="SET NULL"), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_location: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[CreatedAt]


class KnowledgeEntity(Base):
    __tablename__ = "knowledge_entities"
    __table_args__ = (UniqueConstraint("analysis_run_id", "entity_type", "canonical_reference", name="uq_knowledge_entities_run_ref"),)

    id: Mapped[UuidPK]
    analysis_run_id: Mapped[UuidFK] = mapped_column(ForeignKey("knowledge_analysis_runs.id", ondelete="CASCADE"), index=True)
    repository_id: Mapped[UuidFK] = mapped_column(ForeignKey("repository_connections.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_reference: Mapped[str] = mapped_column(String(1000), nullable=False)
    metadata_json: Mapped[JsonObject] = mapped_column("metadata", nullable=False, default=dict)
    created_at: Mapped[CreatedAt]


class KnowledgeRelationship(Base):
    __tablename__ = "knowledge_relationships"
    __table_args__ = (UniqueConstraint("analysis_run_id", "source_entity_id", "target_entity_id", "relationship_type", name="uq_knowledge_relationships_edge"),)

    id: Mapped[UuidPK]
    analysis_run_id: Mapped[UuidFK] = mapped_column(ForeignKey("knowledge_analysis_runs.id", ondelete="CASCADE"), index=True)
    source_entity_id: Mapped[UuidFK] = mapped_column(ForeignKey("knowledge_entities.id", ondelete="CASCADE"), index=True)
    target_entity_id: Mapped[UuidFK] = mapped_column(ForeignKey("knowledge_entities.id", ondelete="CASCADE"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("knowledge_evidence.id", ondelete="SET NULL"), nullable=True)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.7)
    evidence_level: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[CreatedAt]


class KnowledgeGap(Base):
    __tablename__ = "repository_knowledge_gaps"
    __table_args__ = (UniqueConstraint("analysis_run_id", "dedup_key", name="uq_repository_knowledge_gaps_run_dedup"),)

    id: Mapped[UuidPK]
    analysis_run_id: Mapped[UuidFK] = mapped_column(ForeignKey("knowledge_analysis_runs.id", ondelete="CASCADE"), index=True)
    repository_id: Mapped[UuidFK] = mapped_column(ForeignKey("repository_connections.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    affected_component: Mapped[str | None] = mapped_column(String(500), nullable=True)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_question: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open", server_default="open", index=True)
    evidence_references: Mapped[JsonArray]
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class KnowledgeConflict(Base):
    __tablename__ = "repository_knowledge_conflicts"
    __table_args__ = (UniqueConstraint("analysis_run_id", "dedup_key", name="uq_repository_knowledge_conflicts_run_dedup"),)

    id: Mapped[UuidPK]
    analysis_run_id: Mapped[UuidFK] = mapped_column(ForeignKey("knowledge_analysis_runs.id", ondelete="CASCADE"), index=True)
    repository_id: Mapped[UuidFK] = mapped_column(ForeignKey("repository_connections.id", ondelete="CASCADE"), index=True)
    conflict_type: Mapped[str] = mapped_column(String(48), nullable=False)
    claim_a: Mapped[str] = mapped_column(Text, nullable=False)
    claim_b: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_a: Mapped[JsonObject]
    evidence_b: Mapped[JsonObject]
    confidence: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open", server_default="open", index=True)
    possible_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[CreatedAt]


class ProjectAssumption(Base):
    __tablename__ = "repository_project_assumptions"
    __table_args__ = (UniqueConstraint("analysis_run_id", "dedup_key", name="uq_repository_assumptions_run_dedup"),)

    id: Mapped[UuidPK]
    analysis_run_id: Mapped[UuidFK] = mapped_column(ForeignKey("knowledge_analysis_runs.id", ondelete="CASCADE"), index=True)
    repository_id: Mapped[UuidFK] = mapped_column(ForeignKey("repository_connections.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    assumption_type: Mapped[str] = mapped_column(String(48), nullable=False)
    evidence_level: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    verification_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unverified")
    supporting_evidence: Mapped[JsonArray]
    verification_method: Mapped[str] = mapped_column(Text, nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[CreatedAt]
