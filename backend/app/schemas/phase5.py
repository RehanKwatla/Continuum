"""Typed contracts for the Phase 5 readiness, successor and evaluation APIs.

Everything here describes data actually read back from PostgreSQL. Two product
rules are reflected in the shape of these schemas:

* a readiness score is always returned **together** with its blockers, warnings
  and per-requirement evidence, so a number can never be shown on its own;
* an evaluation run always carries the dataset version, the configuration and
  the raw report it was produced from, so a result is reproducible.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    DependencyRiskStatus,
    EvaluationKind,
    KnowledgeGapStatus,
    ReadinessBand,
    RequirementCriticality,
    SuccessorTaskPriority,
    SuccessorTaskStatus,
)

# ---------------------------------------------------------------------------
# Handover readiness (§2, §3)
# ---------------------------------------------------------------------------
class RequirementResultRead(BaseModel):
    """One evaluated readiness requirement and the evidence behind its status."""

    requirement_id: str
    dimension: str
    description: str
    criticality: str
    completion: str
    supporting_claim_ids: list[str] = Field(default_factory=list)
    supporting_source_ids: list[str] = Field(default_factory=list)
    missing_information: str = ""
    evaluation_reason: str = ""
    suggested_resolution: str = ""
    gap_category: str = "other"


class DimensionScoreRead(BaseModel):
    key: str
    label: str
    score: float
    weight: float
    requirement_count: int
    complete_count: int
    criticality_weight: float


class ReadinessIssueRead(BaseModel):
    """A blocker or warning. Only the fields relevant to the issue are present."""

    code: str
    message: str
    requirement_id: str | None = None
    dimension: str | None = None
    criticality: str | None = None
    conflict_id: str | None = None
    property_key: str | None = None


class ReadinessEvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    handover_id: uuid.UUID | None = None
    overall_score: float
    band: ReadinessBand
    weights: dict[str, float] = Field(default_factory=dict)
    dimension_scores: dict[str, DimensionScoreRead] = Field(default_factory=dict)
    requirements: list[RequirementResultRead] = Field(default_factory=list)
    blockers: list[ReadinessIssueRead] = Field(default_factory=list)
    warnings: list[ReadinessIssueRead] = Field(default_factory=list)
    claim_revisions: dict[str, int] = Field(default_factory=dict)
    formula: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ReadinessBandSpec(BaseModel):
    threshold: float
    band: ReadinessBand
    label: str


class ReadinessOverview(BaseModel):
    """The readiness dashboard payload, including its not-yet-evaluated state."""

    project_id: uuid.UUID
    evaluation: ReadinessEvaluationRead | None = None
    bands: list[ReadinessBandSpec] = Field(default_factory=list)
    default_weights: dict[str, float] = Field(default_factory=dict)
    dimension_labels: dict[str, str] = Field(default_factory=dict)
    formula: str
    disclaimer: str


class ReadinessHistoryResponse(BaseModel):
    items: list[ReadinessEvaluationRead] = Field(default_factory=list)
    total: int


class ReadinessEvaluateRequest(BaseModel):
    """Optional weight override. Weights must total 100 if supplied."""

    weights: dict[str, float] | None = None


# ---------------------------------------------------------------------------
# Successor task checklist (§5)
# ---------------------------------------------------------------------------
class SuccessorTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None = None
    priority: SuccessorTaskPriority
    status: SuccessorTaskStatus
    owner: str | None = None
    completion_criteria: str | None = None
    supporting_claim_ids: list[uuid.UUID] = Field(default_factory=list)
    dependency_ids: list[uuid.UUID] = Field(default_factory=list)
    origin: str
    origin_claim_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class SuccessorTaskListResponse(BaseModel):
    items: list[SuccessorTaskRead] = Field(default_factory=list)
    total: int


class SuccessorTaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    priority: SuccessorTaskPriority = SuccessorTaskPriority.MEDIUM
    completion_criteria: str | None = Field(default=None, max_length=2000)


class SuccessorTaskStatusUpdate(BaseModel):
    status: SuccessorTaskStatus
    note: str | None = Field(default=None, max_length=2000)


class SuccessorDeriveResponse(BaseModel):
    created: int
    total: int
    task_ids: list[uuid.UUID] = Field(default_factory=list)
    gaps_considered: int = 0


# ---------------------------------------------------------------------------
# Knowledge dependency analysis (§6)
# ---------------------------------------------------------------------------
class KnowledgeDependencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    dependency_key: str
    entity: str | None = None
    claim_ids: list[uuid.UUID] = Field(default_factory=list)
    related_source_ids: list[uuid.UUID] = Field(default_factory=list)
    involved_people: list[str] = Field(default_factory=list)
    dependency_level: float
    risk_status: DependencyRiskStatus
    #: The reviewer's override when one exists, otherwise ``risk_status``.
    effective_risk_status: DependencyRiskStatus
    evidence_summary: str | None = None
    missing_backup_information: str | None = None
    override: dict[str, Any] = Field(default_factory=dict)
    computed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeDependencyListResponse(BaseModel):
    items: list[KnowledgeDependencyRead] = Field(default_factory=list)
    total: int


class KnowledgeDependencyOverrideRequest(BaseModel):
    risk_status: DependencyRiskStatus | None = Field(
        default=None, description="Set to null to clear an existing override."
    )
    note: str = Field(min_length=1, max_length=2000)


# ---------------------------------------------------------------------------
# Missing knowledge detection (§7)
# ---------------------------------------------------------------------------
class KnowledgeGapRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    gap_key: str
    category: str
    description: str
    criticality: RequirementCriticality
    related_claim_ids: list[uuid.UUID] = Field(default_factory=list)
    related_source_ids: list[uuid.UUID] = Field(default_factory=list)
    suggested_resolution: str | None = None
    status: KnowledgeGapStatus
    created_at: datetime
    updated_at: datetime


class KnowledgeGapListResponse(BaseModel):
    items: list[KnowledgeGapRead] = Field(default_factory=list)
    total: int


class KnowledgeGapStatusUpdate(BaseModel):
    status: KnowledgeGapStatus
    note: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Continuity scorecard (§8)
# ---------------------------------------------------------------------------
class HandoverReadinessSummary(BaseModel):
    evaluation_id: str | None = None
    overall_score: float | None = None
    band: str | None = None
    dimension_scores: dict[str, Any] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    evaluated_at: str | None = None
    blocker_count: int = 0
    warning_count: int = 0


class ContinuityScorecard(BaseModel):
    project_id: str
    handover_readiness: HandoverReadinessSummary
    critical_blockers: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    pending_review_items: int
    conflicts: dict[str, int] = Field(default_factory=dict)
    missing_knowledge: dict[str, int] = Field(default_factory=dict)
    knowledge_dependencies: dict[str, int] = Field(default_factory=dict)
    successor_tasks: dict[str, int] = Field(default_factory=dict)
    source_coverage: dict[str, Any] = Field(default_factory=dict)
    last_evaluation_at: str | None = None
    generated_at: str


# ---------------------------------------------------------------------------
# Successor readiness workspace (§4)
# ---------------------------------------------------------------------------
class WorkspaceEvidenceRef(BaseModel):
    source_name: str
    source_type: str | None = None
    location: str | None = None
    quote: str | None = None
    author: str | None = None
    source_date: str | None = None
    restricted: bool = False


class WorkspaceSection(BaseModel):
    key: str
    title: str
    intro: str
    #: Items are claim-backed (A–I) or task-backed (J); the shapes differ, so the
    #: union is left open rather than pretending they are the same record.
    items: list[dict[str, Any]] = Field(default_factory=list)
    empty_reason: str | None = None
    readiness: dict[str, Any] | None = None
    blockers: list[dict[str, Any]] | None = None
    narrative: list[str] | None = None


class WorkspaceHandoverRef(BaseModel):
    published_version_id: str | None = None
    published_version_number: int | None = None
    published_at: str | None = None


class SuccessorWorkspace(BaseModel):
    project_id: str
    sections: list[WorkspaceSection] = Field(default_factory=list)
    handover: WorkspaceHandoverRef
    counts: dict[str, int] = Field(default_factory=dict)
    open_gaps: list[dict[str, Any]] = Field(default_factory=list)
    disclaimer: str


# ---------------------------------------------------------------------------
# Evaluation framework (§9, §10)
# ---------------------------------------------------------------------------
class EvaluationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID | None = None
    kind: EvaluationKind
    dataset_version: str
    model_version: str | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    failures: list[Any] = Field(default_factory=list)
    report: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class EvaluationRunListResponse(BaseModel):
    items: list[EvaluationRunRead] = Field(default_factory=list)
    total: int


class EvaluationRunRequest(BaseModel):
    model_version: str | None = Field(default=None, max_length=120)


class EvaluationComparison(BaseModel):
    project_id: str
    base_run_id: str
    candidate_run_id: str
    dataset_version: str
    deltas: list[dict[str, Any]] = Field(default_factory=list)
    regressions: list[dict[str, Any]] = Field(default_factory=list)
    improvements: list[dict[str, Any]] = Field(default_factory=list)
    regression_count: int
    improvement_count: int


class SyntheticSeedResponse(BaseModel):
    project_id: uuid.UUID
    name: str
    sources: int
    dataset_version: str


__all__ = [
    "ContinuityScorecard",
    "DimensionScoreRead",
    "EvaluationComparison",
    "EvaluationRunListResponse",
    "EvaluationRunRead",
    "EvaluationRunRequest",
    "HandoverReadinessSummary",
    "KnowledgeDependencyListResponse",
    "KnowledgeDependencyOverrideRequest",
    "KnowledgeDependencyRead",
    "KnowledgeGapListResponse",
    "KnowledgeGapRead",
    "KnowledgeGapStatusUpdate",
    "ReadinessBandSpec",
    "ReadinessEvaluateRequest",
    "ReadinessEvaluationRead",
    "ReadinessHistoryResponse",
    "ReadinessIssueRead",
    "ReadinessOverview",
    "RequirementResultRead",
    "SuccessorDeriveResponse",
    "SuccessorTaskCreateRequest",
    "SuccessorTaskListResponse",
    "SuccessorTaskRead",
    "SuccessorTaskStatusUpdate",
    "SuccessorWorkspace",
    "SyntheticSeedResponse",
    "WorkspaceEvidenceRef",
    "WorkspaceHandoverRef",
    "WorkspaceSection",
]
