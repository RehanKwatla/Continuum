"""Phase 5 persistence: readiness, successor tasks, knowledge risk, evaluation.

Nothing in this module stores a model's opinion as a fact:

* :class:`ReadinessEvaluation` is a *deterministic* snapshot — it records the
  exact weights, the exact claim revisions and the exact requirement results
  that produced one score, so a score can always be re-derived and audited.
* :class:`SuccessorTask` holds actionable work derived from *approved* claims;
  it never invents an owner or a deadline.
* :class:`KnowledgeDependency` records single-person knowledge risk together
  with a reviewer override, and never claims someone is the sole expert merely
  because their name recurs.
* :class:`KnowledgeGap` keeps missing knowledge visible instead of filling it in.
* :class:`EvaluationRun` stores one reproducible evaluation (metrics or a
  successor exercise) so runs can be compared for regressions.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    DependencyRiskStatus,
    EvaluationKind,
    KnowledgeGapStatus,
    ReadinessBand,
    RequirementCriticality,
    SuccessorTaskPriority,
    SuccessorTaskStatus,
)
from app.models.types import (
    CreatedAt,
    JsonArray,
    JsonObject,
    UuidFK,
    UuidPK,
    UpdatedAt,
    sa_enum,
)


class ReadinessEvaluation(Base):
    """One immutable, deterministic readiness assessment of a project."""

    __tablename__ = "readiness_evaluations"
    __table_args__ = (
        Index("ix_readiness_evaluations_project_created", "project_id", "created_at"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    handover_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("handovers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True
    )
    evaluated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    band: Mapped[ReadinessBand] = mapped_column(
        sa_enum(ReadinessBand, "readiness_band", length=24),
        nullable=False,
        index=True,
    )
    #: The configurable weights actually used for this evaluation.
    weights: Mapped[JsonObject] = mapped_column(nullable=False, default=dict)
    #: {dimension: {score, weight, requirement_count, ...}}.
    dimension_scores: Mapped[JsonObject] = mapped_column(nullable=False, default=dict)
    #: Full requirement results (requirement_id, completion, reason, claims, ...).
    requirements: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    #: Blocking issues (unresolved critical conflicts, missing critical knowledge).
    blockers: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    warnings: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    #: {claim_id: revision_number} — the exact claim revisions the score used.
    claim_revisions: Mapped[JsonObject] = mapped_column(nullable=False, default=dict)
    formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[JsonObject] = mapped_column(nullable=False, default=dict)

    created_at: Mapped[CreatedAt]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ReadinessEvaluation project={self.project_id} {self.overall_score}>"


class SuccessorTask(Base):
    """An actionable task derived from approved knowledge (Phase 5 §5)."""

    __tablename__ = "successor_tasks"
    __table_args__ = (
        Index("ix_successor_tasks_project_status", "project_id", "status"),
        UniqueConstraint("project_id", "origin_claim_id", name="uq_successor_tasks_claim"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[SuccessorTaskPriority] = mapped_column(
        sa_enum(SuccessorTaskPriority, "successor_task_priority", length=16),
        nullable=False,
        default=SuccessorTaskPriority.MEDIUM,
    )
    status: Mapped[SuccessorTaskStatus] = mapped_column(
        sa_enum(SuccessorTaskStatus, "successor_task_status", length=16),
        nullable=False,
        default=SuccessorTaskStatus.NOT_STARTED,
        index=True,
    )
    #: Only ever set from an evidence-backed ownership/responsibility claim.
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completion_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    supporting_claim_ids: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    dependency_ids: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    #: "derived" (from an approved claim) or "manual" (successor-authored).
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="derived")
    origin_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SuccessorTask {self.id} {self.status}>"


class KnowledgeDependency(Base):
    """Concentration of project knowledge on one person or a small group (§6)."""

    __tablename__ = "knowledge_dependencies"
    __table_args__ = (
        UniqueConstraint("project_id", "dependency_key", name="uq_knowledge_dependencies_key"),
        Index("ix_knowledge_dependencies_project_risk", "project_id", "risk_status"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    #: Stable key for the analysed subject (usually the entity, else a topic).
    dependency_key: Mapped[str] = mapped_column(String(300), nullable=False)
    entity: Mapped[str | None] = mapped_column(String(300), nullable=True)
    claim_ids: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    related_source_ids: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    involved_people: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    #: 0..1 concentration of responsibility on the leading person.
    dependency_level: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_status: Mapped[DependencyRiskStatus] = mapped_column(
        sa_enum(DependencyRiskStatus, "dependency_risk_status", length=16),
        nullable=False,
        default=DependencyRiskStatus.UNKNOWN,
        index=True,
    )
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_backup_information: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Reviewer override: {"risk_status", "note", "by_id", "at"}.
    override: Mapped[JsonObject] = mapped_column(nullable=False, default=dict)
    computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    @property
    def effective_risk_status(self) -> DependencyRiskStatus:
        """The reviewer's override when one exists, otherwise the computed risk.

        The computed ``risk_status`` is never overwritten, so the engine's own
        assessment and the human override remain separately auditable.
        """
        override = (self.override or {}).get("risk_status")
        if override:
            try:
                return DependencyRiskStatus(override)
            except ValueError:  # pragma: no cover - defensive
                return self.risk_status
        return self.risk_status

    def __repr__(self) -> str:  # pragma: no cover
        return f"<KnowledgeDependency {self.dependency_key} {self.risk_status}>"


class KnowledgeGap(Base):
    """A detected absence of required project knowledge (Phase 5 §7)."""

    __tablename__ = "knowledge_gaps"
    __table_args__ = (
        UniqueConstraint("project_id", "gap_key", name="uq_knowledge_gaps_key"),
        Index("ix_knowledge_gaps_project_status", "project_id", "status"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    #: Stable key, normally the readiness requirement id that surfaced the gap.
    gap_key: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    criticality: Mapped[RequirementCriticality] = mapped_column(
        sa_enum(RequirementCriticality, "gap_criticality", length=16),
        nullable=False,
        default=RequirementCriticality.IMPORTANT,
    )
    related_claim_ids: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    related_source_ids: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    suggested_resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[KnowledgeGapStatus] = mapped_column(
        sa_enum(KnowledgeGapStatus, "knowledge_gap_status", length=16),
        nullable=False,
        default=KnowledgeGapStatus.OPEN,
        index=True,
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<KnowledgeGap {self.gap_key} {self.status}>"


class EvaluationRun(Base):
    """A reproducible evaluation result (Phase 5 §9, §10)."""

    __tablename__ = "evaluation_runs"
    __table_args__ = (
        Index("ix_evaluation_runs_project_created", "project_id", "created_at"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[EvaluationKind] = mapped_column(
        sa_enum(EvaluationKind, "evaluation_kind", length=24),
        nullable=False,
        default=EvaluationKind.METRICS,
        index=True,
    )
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    configuration: Mapped[JsonObject] = mapped_column(nullable=False, default=dict)
    metrics: Mapped[JsonObject] = mapped_column(nullable=False, default=dict)
    failures: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    #: Free-form report body (used by the successor exercise).
    report: Mapped[JsonObject] = mapped_column(nullable=False, default=dict)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[CreatedAt]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EvaluationRun {self.kind} {self.dataset_version}>"


__all__ = [
    "ReadinessEvaluation",
    "SuccessorTask",
    "KnowledgeDependency",
    "KnowledgeGap",
    "EvaluationRun",
]
