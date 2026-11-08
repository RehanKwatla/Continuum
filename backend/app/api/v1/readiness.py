"""Phase 5 API: readiness, successor experience, knowledge risk, evaluation.

This router exposes the deterministic engines built for Phase 5. Three product
boundaries are enforced here and not only in the UI:

* **Every endpoint re-checks project access.** Reads resolve at ``VIEWER``,
  mutations at ``MEMBER`` and evaluation/override operations at ``ADMIN``, all
  through :func:`resolve_project_access`, so workspace isolation is applied
  uniformly and a non-member sees ``404`` rather than another tenant's data.
* **The score is never returned alone.** A readiness response always carries its
  blockers, warnings and per-requirement evidence.
* **Nothing is fabricated.** Deterministic engines compute the numbers; the
  evaluation endpoints read real rows back and persist reproducible runs.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select, text

from app.core.dependencies import CurrentUser, DbSession, resolve_project_access, resolve_workspace_access
from app.core.errors import NotFoundError
from app.evaluation.ground_truth import GROUND_TRUTH, GROUND_TRUTH_PROJECT_NAME
from app.evaluation.service import EvaluationService
from app.evaluation.synthetic import SYNTHETIC_SOURCES, seed_synthetic_evaluation_project
from app.models.claim import Claim
from app.models.enums import (
    EvaluationKind,
    KnowledgeGapStatus,
    ProcessingRunStatus,
    ProcessingStatus,
    SuccessorTaskStatus,
    WorkspaceRole,
)
from app.models.processing_run import ProcessingRun
from app.models.source import Source
from app.schemas.phase5 import (
    ContinuityScorecard,
    EvaluationComparison,
    EvaluationRunListResponse,
    EvaluationRunRead,
    EvaluationRunRequest,
    KnowledgeDependencyListResponse,
    KnowledgeDependencyOverrideRequest,
    KnowledgeDependencyRead,
    KnowledgeGapListResponse,
    KnowledgeGapRead,
    KnowledgeGapStatusUpdate,
    ReadinessBandSpec,
    ReadinessEvaluateRequest,
    ReadinessEvaluationRead,
    ReadinessHistoryResponse,
    ReadinessOverview,
    SuccessorDeriveResponse,
    SuccessorTaskCreateRequest,
    SuccessorTaskListResponse,
    SuccessorTaskRead,
    SuccessorTaskStatusUpdate,
    SuccessorWorkspace,
    SyntheticSeedResponse,
)
from app.services.continuity_service import ContinuityService
from app.services.knowledge_service import KnowledgeRiskService
from app.services.readiness_catalog import (
    DEFAULT_BANDS,
    DIMENSION_LABELS,
    SCORING_FORMULA,
    default_weights,
)
from app.services.readiness_service import ReadinessService
from app.services.successor_service import SuccessorService
from app.services.successor_workspace_service import build_workspace

router = APIRouter(prefix="/projects", tags=["phase5"])
workspace_router = APIRouter(prefix="/workspaces", tags=["phase5"])

_BAND_LABELS: dict[str, str] = {
    "strong": "Strong handover readiness",
    "mostly_ready": "Mostly ready, some gaps",
    "needs_review": "Needs additional review",
    "not_ready": "Not ready",
}

_READINESS_DISCLAIMER = (
    "The readiness score measures how complete and trustworthy the approved "
    "knowledge is. It is not proof that a successor will succeed, and it never "
    "conceals a blocker."
)

_WORKSPACE_DISCLAIMER = (
    "This workspace contains only knowledge a human reviewer has approved, "
    "linked back to its source evidence. Restricted source material is excluded."
)


# ---------------------------------------------------------------------------
# Handover readiness (§2, §3, §13A)
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/readiness",
    response_model=ReadinessOverview,
    summary="The latest handover readiness assessment (and its not-yet-run state)",
)
def get_readiness(project_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ReadinessOverview:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    evaluation = ReadinessService(db).latest(project_id)
    return ReadinessOverview(
        project_id=project_id,
        evaluation=(
            ReadinessEvaluationRead.model_validate(evaluation) if evaluation else None
        ),
        bands=[
            ReadinessBandSpec(threshold=threshold, band=band, label=_BAND_LABELS.get(band, band))
            for threshold, band in DEFAULT_BANDS
        ],
        default_weights=default_weights(),
        dimension_labels={dimension.value: label for dimension, label in DIMENSION_LABELS.items()},
        formula=SCORING_FORMULA,
        disclaimer=_READINESS_DISCLAIMER,
    )


@router.post(
    "/{project_id}/readiness/evaluate",
    response_model=ReadinessEvaluationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Run the deterministic readiness engine and persist the snapshot",
)
def evaluate_readiness(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    payload: ReadinessEvaluateRequest | None = None,
) -> ReadinessEvaluationRead:
    project, _role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    service = ReadinessService(db)
    evaluation = service.evaluate(
        project_id,
        user_id=user.id,
        workspace_id=project.workspace_id,
        weights=payload.weights if payload else None,
        source="manual",
    )
    db.commit()
    return ReadinessEvaluationRead.model_validate(evaluation)


@router.get(
    "/{project_id}/readiness/history",
    response_model=ReadinessHistoryResponse,
    summary="The readiness score history (newest first)",
)
def readiness_history(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
) -> ReadinessHistoryResponse:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    rows = ReadinessService(db).history(project_id, limit=limit)
    return ReadinessHistoryResponse(
        items=[ReadinessEvaluationRead.model_validate(row) for row in rows], total=len(rows)
    )


@router.get(
    "/{project_id}/readiness/{evaluation_id}",
    response_model=ReadinessEvaluationRead,
    summary="One stored readiness evaluation",
)
def get_readiness_evaluation(
    project_id: uuid.UUID, evaluation_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ReadinessEvaluationRead:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    evaluation = ReadinessService(db).get(project_id, evaluation_id)
    return ReadinessEvaluationRead.model_validate(evaluation)


# ---------------------------------------------------------------------------
# Successor task checklist (§5, §13D)
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/successor-tasks",
    response_model=SuccessorTaskListResponse,
    summary="The successor task checklist",
)
def list_successor_tasks(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    task_status: SuccessorTaskStatus | None = Query(default=None, alias="status"),
) -> SuccessorTaskListResponse:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    rows = SuccessorService(db).list_tasks(project_id, status=task_status)
    return SuccessorTaskListResponse(
        items=[SuccessorTaskRead.model_validate(row) for row in rows], total=len(rows)
    )


@router.post(
    "/{project_id}/successor-tasks/derive",
    response_model=SuccessorDeriveResponse,
    summary="Derive actionable tasks from approved knowledge (idempotent)",
)
def derive_successor_tasks(
    project_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> SuccessorDeriveResponse:
    project, _role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    knowledge = KnowledgeRiskService(db)
    open_gaps = knowledge.list_gaps(project_id, status=KnowledgeGapStatus.OPEN)
    gap_dicts = [
        {
            "gap_key": gap.gap_key,
            "category": gap.category,
            "description": gap.description,
            "criticality": gap.criticality.value,
            "suggested_resolution": gap.suggested_resolution,
        }
        for gap in open_gaps
    ]
    result = SuccessorService(db).derive(
        project_id,
        user_id=user.id,
        workspace_id=project.workspace_id,
        gaps=gap_dicts,
    )
    db.commit()
    return SuccessorDeriveResponse(
        created=result["created"],
        total=result["total"],
        task_ids=list(result["task_ids"]),
        gaps_considered=len(open_gaps),
    )


@router.post(
    "/{project_id}/successor-tasks",
    response_model=SuccessorTaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a successor-authored task (no owner or deadline is invented)",
)
def create_successor_task(
    project_id: uuid.UUID,
    payload: SuccessorTaskCreateRequest,
    user: CurrentUser,
    db: DbSession,
) -> SuccessorTaskRead:
    project, _role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    task = SuccessorService(db).add_manual_task(
        project_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        completion_criteria=payload.completion_criteria,
        user_id=user.id,
        workspace_id=project.workspace_id,
    )
    db.commit()
    return SuccessorTaskRead.model_validate(task)


@router.get(
    "/{project_id}/successor-tasks/{task_id}",
    response_model=SuccessorTaskRead,
    summary="One successor task",
)
def get_successor_task(
    project_id: uuid.UUID, task_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> SuccessorTaskRead:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    return SuccessorTaskRead.model_validate(SuccessorService(db).get(project_id, task_id))


@router.patch(
    "/{project_id}/successor-tasks/{task_id}",
    response_model=SuccessorTaskRead,
    summary="Update a task's progress (recorded in the audit trail)",
)
def update_successor_task(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: SuccessorTaskStatusUpdate,
    user: CurrentUser,
    db: DbSession,
) -> SuccessorTaskRead:
    project, _role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    task = SuccessorService(db).update_status(
        project_id,
        task_id,
        status=payload.status,
        user_id=user.id,
        workspace_id=project.workspace_id,
        note=payload.note,
    )
    db.commit()
    return SuccessorTaskRead.model_validate(task)


# ---------------------------------------------------------------------------
# Knowledge dependency analysis (§6, §13C)
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/knowledge-dependencies",
    response_model=KnowledgeDependencyListResponse,
    summary="Single-person knowledge dependencies found in approved knowledge",
)
def list_knowledge_dependencies(
    project_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> KnowledgeDependencyListResponse:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    rows = KnowledgeRiskService(db).list_dependencies(project_id)
    return KnowledgeDependencyListResponse(
        items=[KnowledgeDependencyRead.model_validate(row) for row in rows], total=len(rows)
    )


@router.post(
    "/{project_id}/knowledge-dependencies/analyse",
    response_model=KnowledgeDependencyListResponse,
    summary="Recompute knowledge concentration (requires sourced evidence)",
)
def analyse_knowledge_dependencies(
    project_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> KnowledgeDependencyListResponse:
    project, _role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    rows = KnowledgeRiskService(db).analyse_dependencies(
        project_id, user_id=user.id, workspace_id=project.workspace_id
    )
    db.commit()
    return KnowledgeDependencyListResponse(
        items=[KnowledgeDependencyRead.model_validate(row) for row in rows], total=len(rows)
    )


@router.get(
    "/{project_id}/knowledge-dependencies/{dependency_id}",
    response_model=KnowledgeDependencyRead,
    summary="One knowledge dependency record",
)
def get_knowledge_dependency(
    project_id: uuid.UUID, dependency_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> KnowledgeDependencyRead:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    record = KnowledgeRiskService(db).get_dependency(project_id, dependency_id)
    return KnowledgeDependencyRead.model_validate(record)


@router.post(
    "/{project_id}/knowledge-dependencies/{dependency_id}/override",
    response_model=KnowledgeDependencyRead,
    summary="Override a computed knowledge risk (audited; never deletes the computation)",
)
def override_knowledge_dependency(
    project_id: uuid.UUID,
    dependency_id: uuid.UUID,
    payload: KnowledgeDependencyOverrideRequest,
    user: CurrentUser,
    db: DbSession,
) -> KnowledgeDependencyRead:
    project, _role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.ADMIN
    )
    record = KnowledgeRiskService(db).override_dependency(
        project_id,
        dependency_id,
        risk_status=payload.risk_status,
        note=payload.note,
        user_id=user.id,
        workspace_id=project.workspace_id,
    )
    db.commit()
    return KnowledgeDependencyRead.model_validate(record)


# ---------------------------------------------------------------------------
# Missing knowledge detection (§7)
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/knowledge-gaps",
    response_model=KnowledgeGapListResponse,
    summary="Detected missing-knowledge gaps",
)
def list_knowledge_gaps(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    gap_status: KnowledgeGapStatus | None = Query(default=None, alias="status"),
) -> KnowledgeGapListResponse:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    rows = KnowledgeRiskService(db).list_gaps(project_id, status=gap_status)
    return KnowledgeGapListResponse(
        items=[KnowledgeGapRead.model_validate(row) for row in rows], total=len(rows)
    )


@router.post(
    "/{project_id}/knowledge-gaps/detect",
    response_model=KnowledgeGapListResponse,
    summary="Detect gaps by comparing requirements against approved knowledge",
)
def detect_knowledge_gaps(
    project_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> KnowledgeGapListResponse:
    project, _role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    readiness = ReadinessService(db).latest(project_id)
    if readiness is None:
        raise NotFoundError(
            "Run a readiness evaluation first; gaps are derived from readiness requirements."
        )
    risk = KnowledgeRiskService(db)
    rows = risk.detect_gaps(
        project_id,
        requirements=readiness.requirements or [],
        dependencies=risk.list_dependencies(project_id),
        user_id=user.id,
        workspace_id=project.workspace_id,
    )
    db.commit()
    return KnowledgeGapListResponse(
        items=[KnowledgeGapRead.model_validate(row) for row in rows], total=len(rows)
    )


@router.get(
    "/{project_id}/knowledge-gaps/{gap_id}",
    response_model=KnowledgeGapRead,
    summary="One knowledge gap",
)
def get_knowledge_gap(
    project_id: uuid.UUID, gap_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> KnowledgeGapRead:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    return KnowledgeGapRead.model_validate(KnowledgeRiskService(db).get_gap(project_id, gap_id))


@router.patch(
    "/{project_id}/knowledge-gaps/{gap_id}",
    response_model=KnowledgeGapRead,
    summary="Move a gap through its workflow (audited; the gap is never deleted)",
)
def update_knowledge_gap(
    project_id: uuid.UUID,
    gap_id: uuid.UUID,
    payload: KnowledgeGapStatusUpdate,
    user: CurrentUser,
    db: DbSession,
) -> KnowledgeGapRead:
    project, _role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    gap = KnowledgeRiskService(db).update_gap_status(
        project_id,
        gap_id,
        status=payload.status,
        user_id=user.id,
        workspace_id=project.workspace_id,
        note=payload.note,
    )
    db.commit()
    return KnowledgeGapRead.model_validate(gap)


# ---------------------------------------------------------------------------
# Continuity scorecard (§8)
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/scorecard",
    response_model=ContinuityScorecard,
    summary="The consolidated project continuity scorecard",
)
def get_scorecard(project_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ContinuityScorecard:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    payload = ContinuityService(db).scorecard(project_id)
    return ContinuityScorecard.model_validate(payload)


# ---------------------------------------------------------------------------
# Successor workspace (§4, §13B)
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/successor-workspace",
    response_model=SuccessorWorkspace,
    summary="The guided successor onboarding workspace",
)
def get_successor_workspace(
    project_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> SuccessorWorkspace:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    payload = build_workspace(db, project_id)
    payload["disclaimer"] = _WORKSPACE_DISCLAIMER
    return SuccessorWorkspace.model_validate(payload)


# ---------------------------------------------------------------------------
# Successor readiness exercise (§10)
# ---------------------------------------------------------------------------
@router.post(
    "/{project_id}/successor-exercise",
    response_model=EvaluationRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Run the deterministic successor readiness exercise",
)
def run_successor_exercise(
    project_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> EvaluationRunRead:
    project, _role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    run = ContinuityService(db).run_successor_exercise(
        project_id, user_id=user.id, workspace_id=project.workspace_id
    )
    db.commit()
    return EvaluationRunRead.model_validate(run)


@router.get(
    "/{project_id}/successor-exercise",
    response_model=EvaluationRunRead,
    summary="The most recent successor readiness exercise",
)
def get_successor_exercise(
    project_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> EvaluationRunRead:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    run = EvaluationService(db).latest_run(project_id, kind=EvaluationKind.SUCCESSOR_EXERCISE)
    if run is None:
        raise NotFoundError("No successor exercise has been run for this project yet.")
    return EvaluationRunRead.model_validate(run)


# ---------------------------------------------------------------------------
# Evaluation framework (§9, §13E)
# ---------------------------------------------------------------------------
@router.post(
    "/{project_id}/evaluation/runs",
    response_model=EvaluationRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Run the reproducible evaluation and persist the result",
)
def run_evaluation(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    payload: EvaluationRunRequest | None = None,
) -> EvaluationRunRead:
    project, _role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.ADMIN
    )
    run = EvaluationService(db).run_metrics(
        project_id,
        user_id=user.id,
        workspace_id=project.workspace_id,
        model_version=payload.model_version if payload else None,
    )
    db.commit()
    return EvaluationRunRead.model_validate(run)


@router.get(
    "/{project_id}/evaluation/runs",
    response_model=EvaluationRunListResponse,
    summary="List evaluation runs (newest first)",
)
def list_evaluation_runs(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    kind: EvaluationKind | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> EvaluationRunListResponse:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    rows, total = EvaluationService(db).list_runs(
        project_id, kind=kind, page=page, page_size=page_size
    )
    return EvaluationRunListResponse(
        items=[EvaluationRunRead.model_validate(row) for row in rows], total=total
    )


@router.get(
    "/{project_id}/evaluation/compare",
    response_model=EvaluationComparison,
    summary="Compare two evaluation runs to detect regressions",
)
def compare_evaluation_runs(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    base: uuid.UUID = Query(..., description="Baseline run id."),
    candidate: uuid.UUID = Query(..., description="Run to compare against the baseline."),
) -> EvaluationComparison:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    payload = EvaluationService(db).compare(
        project_id, base_run_id=base, candidate_run_id=candidate
    )
    return EvaluationComparison.model_validate(payload)


@router.get(
    "/{project_id}/evaluation/runs/{run_id}",
    response_model=EvaluationRunRead,
    summary="One evaluation run, with its full report",
)
def get_evaluation_run(
    project_id: uuid.UUID, run_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> EvaluationRunRead:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    run = EvaluationService(db).get_run(project_id, run_id)
    return EvaluationRunRead.model_validate(run)


# ---------------------------------------------------------------------------
# System health and processing status (§12, §13F)
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/system-health",
    summary="Processing status, source health and recent failures for a project",
)
def project_system_health(
    project_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )

    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # pragma: no cover - depends on the environment
        database = "unavailable"

    source_rows = db.execute(
        select(Source.processing_status, func.count())
        .where(Source.project_id == project_id)
        .group_by(Source.processing_status)
    ).all()
    sources_by_status = {str(s): int(c) for s, c in source_rows}

    run_rows = db.execute(
        select(ProcessingRun.status, func.count())
        .where(ProcessingRun.project_id == project_id)
        .group_by(ProcessingRun.status)
    ).all()
    runs_by_status = {str(s): int(c) for s, c in run_rows}

    recent_runs = list(
        db.execute(
            select(ProcessingRun)
            .where(ProcessingRun.project_id == project_id)
            .order_by(ProcessingRun.created_at.desc())
            .limit(10)
        ).scalars().all()
    )

    claim_rows = db.execute(
        select(Claim.status, func.count())
        .where(Claim.project_id == project_id)
        .group_by(Claim.status)
    ).all()
    claims_by_status = {str(s): int(c) for s, c in claim_rows}

    failures = [
        {
            "run_id": str(run.id),
            "status": run.status.value,
            "error": run.error_message,
            "errors": list(run.errors or [])[:10],
            "created_at": run.created_at.isoformat(),
        }
        for run in recent_runs
        if run.status in {ProcessingRunStatus.FAILED, ProcessingRunStatus.PARTIAL}
        or run.error_message
        or run.errors
    ]

    return {
        "project_id": str(project_id),
        "database": database,
        "status": "ok" if database == "ok" else "degraded",
        "sources_by_status": sources_by_status,
        "processing_runs_by_status": runs_by_status,
        "claims_by_status": claims_by_status,
        "recent_failures": failures,
        "recent_runs": [
            {
                "run_id": str(run.id),
                "status": run.status.value,
                "source_count": run.source_count,
                "claim_count": run.claim_count,
                "verified_count": run.verified_count,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "created_at": run.created_at.isoformat(),
            }
            for run in recent_runs
        ],
    }


# ---------------------------------------------------------------------------
# Synthetic evaluation dataset seeding (§9, §15) — workspace scoped
# ---------------------------------------------------------------------------
@workspace_router.post(
    "/{workspace_id}/evaluation/synthetic-project",
    response_model=SyntheticSeedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Seed the ground-truth project's source corpus for evaluation",
)
def seed_synthetic_project(
    workspace_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> SyntheticSeedResponse:
    resolve_workspace_access(
        db, workspace_id=workspace_id, user=user, required_role=WorkspaceRole.ADMIN
    )
    project = seed_synthetic_evaluation_project(db, workspace_id=workspace_id)
    db.commit()
    return SyntheticSeedResponse(
        project_id=project.id,
        name=project.name or GROUND_TRUTH_PROJECT_NAME,
        sources=len(SYNTHETIC_SOURCES),
        dataset_version=GROUND_TRUTH.version,
    )


__all__ = ["router", "workspace_router"]
