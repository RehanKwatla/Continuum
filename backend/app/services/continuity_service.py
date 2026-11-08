"""Project continuity scorecard and successor readiness exercise (§8, §10).

Both are *read models* over records that already exist. Nothing here is
decorative: every number is a count or an aggregate taken from the database at
request time, and every scorecard item can be traced back to the records that
produced it.

The successor readiness exercise is an additional, **limited** quality check. It
answers a fixed, project-specific question set from the approved knowledge and
reports which questions the handover can and cannot answer. It does not claim to
simulate human competence.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.conflict import Conflict
from app.models.enums import (
    AWAITING_REVIEW_STATUSES,
    GITHUB_SOURCE_TYPES,
    ClaimStatus,
    ClaimType,
    ConflictStatus,
    DependencyRiskStatus,
    EvaluationKind,
    ExerciseOutcome,
    KnowledgeGapStatus,
    ProcessingStatus,
    SuccessorTaskStatus,
)
from app.models.evidence import Evidence
from app.models.phase5 import (
    EvaluationRun,
    KnowledgeDependency,
    KnowledgeGap,
    ReadinessEvaluation,
    SuccessorTask,
)
from app.models.source import Source
from app.services import audit_service
from app.services.readiness_service import ReadinessService, build_context

logger = logging.getLogger("continuum.continuity")

_APPROVED = ClaimStatus.VERIFIED

#: The dataset version stamped on the deterministic successor exercise.
EXERCISE_DATASET_VERSION = "successor-exercise-v1"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ContinuityService:
    """Builds the continuity scorecard and runs the successor exercise."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # §8 — consolidated continuity scorecard
    # ------------------------------------------------------------------
    def scorecard(self, project_id: uuid.UUID) -> dict[str, Any]:
        readiness = ReadinessService(self.db).latest(project_id)

        approved_claim_count = self._count(
            select(func.count()).select_from(Claim).where(
                Claim.project_id == project_id, Claim.status == _APPROVED
            )
        )
        pending_review = self._count(
            select(func.count()).select_from(Claim).where(
                Claim.project_id == project_id,
                Claim.status.in_([status.value for status in AWAITING_REVIEW_STATUSES]),
            )
        )
        approved_with_evidence = self._count(
            select(func.count(func.distinct(Evidence.claim_id)))
            .select_from(Evidence)
            .join(Claim, Claim.id == Evidence.claim_id)
            .where(Claim.project_id == project_id, Claim.status == _APPROVED)
        )
        open_conflicts = self._count(
            select(func.count()).select_from(Conflict).where(
                Conflict.project_id == project_id, Conflict.status == ConflictStatus.OPEN
            )
        )
        total_conflicts = self._count(
            select(func.count()).select_from(Conflict).where(Conflict.project_id == project_id)
        )
        open_gaps = self._count(
            select(func.count()).select_from(KnowledgeGap).where(
                KnowledgeGap.project_id == project_id,
                KnowledgeGap.status == KnowledgeGapStatus.OPEN,
            )
        )
        accepted_risk_gaps = self._count(
            select(func.count()).select_from(KnowledgeGap).where(
                KnowledgeGap.project_id == project_id,
                KnowledgeGap.status == KnowledgeGapStatus.ACCEPTED_RISK,
            )
        )
        high_risk_dependencies = self._count(
            select(func.count()).select_from(KnowledgeDependency).where(
                KnowledgeDependency.project_id == project_id,
                KnowledgeDependency.risk_status == DependencyRiskStatus.HIGH,
            )
        )
        unknown_dependencies = self._count(
            select(func.count()).select_from(KnowledgeDependency).where(
                KnowledgeDependency.project_id == project_id,
                KnowledgeDependency.risk_status == DependencyRiskStatus.UNKNOWN,
            )
        )

        task_counts = {
            status.value: self._count(
                select(func.count()).select_from(SuccessorTask).where(
                    SuccessorTask.project_id == project_id, SuccessorTask.status == status
                )
            )
            for status in SuccessorTaskStatus
        }
        task_total = sum(task_counts.values())

        source_rows = self.db.execute(
            select(Source.source_type, func.count())
            .where(Source.project_id == project_id)
            .group_by(Source.source_type)
        ).all()
        sources_by_type = {str(source_type): int(count) for source_type, count in source_rows}
        total_sources = sum(sources_by_type.values())
        processed_sources = self._count(
            select(func.count()).select_from(Source).where(
                Source.project_id == project_id,
                Source.processing_status == ProcessingStatus.COMPLETED,
            )
        )
        github_sources = sum(
            sources_by_type.get(str(source_type), 0) for source_type in GITHUB_SOURCE_TYPES
        )

        coverage = (
            round(100.0 * approved_with_evidence / approved_claim_count, 2)
            if approved_claim_count
            else 0.0
        )

        blockers = list(readiness.blockers or []) if readiness else []
        warnings = list(readiness.warnings or []) if readiness else []

        return {
            "project_id": str(project_id),
            "handover_readiness": {
                "evaluation_id": str(readiness.id) if readiness else None,
                "overall_score": readiness.overall_score if readiness else None,
                "band": readiness.band.value if readiness else None,
                "dimension_scores": dict(readiness.dimension_scores or {}) if readiness else {},
                "weights": dict(readiness.weights or {}) if readiness else {},
                "evaluated_at": readiness.created_at.isoformat() if readiness else None,
                "blocker_count": len(blockers),
                "warning_count": len(warnings),
            },
            "critical_blockers": blockers,
            "warnings": warnings,
            "pending_review_items": pending_review,
            "conflicts": {"open": open_conflicts, "total": total_conflicts},
            "missing_knowledge": {"open": open_gaps, "accepted_risk": accepted_risk_gaps},
            "knowledge_dependencies": {
                "high_risk": high_risk_dependencies,
                "unknown": unknown_dependencies,
            },
            "successor_tasks": {**task_counts, "total": task_total},
            "source_coverage": {
                "total_sources": total_sources,
                "processed_sources": processed_sources,
                "github_sources": github_sources,
                "sources_by_type": sources_by_type,
                "approved_claims": approved_claim_count,
                "approved_claims_with_evidence": approved_with_evidence,
                "evidence_coverage_percent": coverage,
            },
            "last_evaluation_at": readiness.created_at.isoformat() if readiness else None,
            "generated_at": _now().isoformat(),
        }

    def _count(self, query: Any) -> int:
        return int(self.db.execute(query).scalar_one())

    # ------------------------------------------------------------------
    # §10 — successor readiness exercise
    # ------------------------------------------------------------------
    def run_successor_exercise(
        self,
        project_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> EvaluationRun:
        """Answer a fixed, project-specific question set from approved knowledge."""
        ctx = build_context(self.db, project_id)
        open_conflict_claims = set(ctx.conflicted_claim_ids)

        results: list[dict[str, Any]] = []
        for question in _QUESTIONS:
            results.append(question(ctx, open_conflict_claims))

        attempted = len(results)
        completed = sum(
            1 for item in results if item["outcome"] == ExerciseOutcome.COMPLETED.value
        )
        blocked = sum(
            1 for item in results if item["outcome"] == ExerciseOutcome.BLOCKED.value
        )
        missing = sum(
            1
            for item in results
            if item["outcome"] == ExerciseOutcome.MISSING_INFORMATION.value
        )
        score = round(100.0 * completed / attempted, 2) if attempted else 0.0

        metrics = {
            "tasks_attempted": attempted,
            "tasks_completed": completed,
            "tasks_blocked": blocked,
            "tasks_missing_information": missing,
            "exercise_score": score,
        }
        failures = [
            {"question_id": item["question_id"], "reason": item["explanation"]}
            for item in results
            if item["outcome"] != ExerciseOutcome.COMPLETED.value
        ]
        report = {
            "dataset_version": EXERCISE_DATASET_VERSION,
            "disclaimer": (
                "This is a deterministic evidence check over approved knowledge. It "
                "does not simulate human competence and is not a substitute for real "
                "successor testing."
            ),
            "questions": results,
        }

        run = EvaluationRun(
            project_id=project_id,
            kind=EvaluationKind.SUCCESSOR_EXERCISE,
            dataset_version=EXERCISE_DATASET_VERSION,
            model_version=None,
            configuration={"approved_claims": ctx.approved_total},
            metrics=metrics,
            failures=failures,
            report=report,
            created_by_id=user_id,
        )
        self.db.add(run)
        self.db.flush()
        audit_service.record(
            self.db,
            action="successor_exercise_run",
            user_id=user_id,
            workspace_id=workspace_id,
            resource_type="evaluation_run",
            resource_id=run.id,
            metadata={
                "project_id": str(project_id),
                "score": score,
                "completed": completed,
                "blocked": blocked,
                "missing": missing,
            },
        )
        return run


# ---------------------------------------------------------------------------
# The deterministic question set
# ---------------------------------------------------------------------------
def _approved_claims(ctx: Any, *claim_types: ClaimType) -> list[Claim]:
    found: list[Claim] = []
    for claim_type in claim_types:
        found.extend(ctx.approved_by_type.get(claim_type, []))
    return found


def _with_keywords(claims: list[Claim], keywords: tuple[str, ...]) -> list[Claim]:
    matched: list[Claim] = []
    for claim in claims:
        haystack = f"{claim.text} {claim.entity or ''}".lower()
        if any(keyword in haystack for keyword in keywords):
            matched.append(claim)
    return matched


def _answer(
    question_id: str,
    prompt: str,
    claims: list[Claim],
    conflicted: set[uuid.UUID],
    *,
    missing_explanation: str,
) -> dict[str, Any]:
    """Turn a set of supporting claims into a deterministic exercise answer."""
    if not claims:
        return {
            "question_id": question_id,
            "prompt": prompt,
            "outcome": ExerciseOutcome.MISSING_INFORMATION.value,
            "answer": None,
            "supporting_claim_ids": [],
            "explanation": missing_explanation,
        }
    if any(claim.id in conflicted for claim in claims):
        return {
            "question_id": question_id,
            "prompt": prompt,
            "outcome": ExerciseOutcome.BLOCKED.value,
            "answer": None,
            "supporting_claim_ids": sorted(str(claim.id) for claim in claims),
            "explanation": (
                "The approved knowledge that would answer this is part of an "
                "unresolved conflict and cannot be relied on yet."
            ),
        }
    primary = claims[0]
    return {
        "question_id": question_id,
        "prompt": prompt,
        "outcome": ExerciseOutcome.COMPLETED.value,
        "answer": primary.text,
        "supporting_claim_ids": sorted(str(claim.id) for claim in claims),
        "explanation": (
            f"Answered from {len(claims)} approved claim(s) with supporting evidence."
        ),
    }


def _q_repository(ctx: Any, conflicted: set[uuid.UUID]) -> dict[str, Any]:
    repository_types = {str(item) for item in GITHUB_SOURCE_TYPES}
    present = sorted(repository_types.intersection(ctx.source_types_present))
    if present:
        return {
            "question_id": "locate_repository",
            "prompt": "Locate the main application repository.",
            "outcome": ExerciseOutcome.COMPLETED.value,
            "answer": f"Repository sources are connected ({', '.join(present)}).",
            "supporting_claim_ids": [],
            "explanation": "A connected repository source is available to the successor.",
        }
    claims = _with_keywords(
        _approved_claims(ctx, ClaimType.DEPENDENCY), ("repo", "repository", "github")
    )
    return _answer(
        "locate_repository",
        "Locate the main application repository.",
        claims,
        conflicted,
        missing_explanation="No repository reference is documented or connected.",
    )


def _q_external_service(ctx: Any, conflicted: set[uuid.UUID]) -> dict[str, Any]:
    claims = _with_keywords(
        _approved_claims(ctx, ClaimType.DEPENDENCY),
        ("service", "api", "external", "third-party", "stripe", "payment", "gemini", "supabase"),
    )
    return _answer(
        "identify_external_service",
        "Identify an external service the project depends on.",
        claims,
        conflicted,
        missing_explanation="No external service dependency is documented.",
    )


def _q_retry_policy(ctx: Any, conflicted: set[uuid.UUID]) -> dict[str, Any]:
    claims = _with_keywords(
        _approved_claims(
            ctx,
            ClaimType.TECHNICAL_CONSTRAINT,
            ClaimType.OPERATIONAL_PROCEDURE,
            ClaimType.DEPENDENCY,
        ),
        ("retry", "retries", "backoff", "back-off"),
    )
    return _answer(
        "find_retry_policy",
        "Find the documented retry policy.",
        claims,
        conflicted,
        missing_explanation="No retry policy is documented in approved knowledge.",
    )


def _q_deployment_blocker(ctx: Any, conflicted: set[uuid.UUID]) -> dict[str, Any]:
    claims = _with_keywords(
        _approved_claims(ctx, ClaimType.RISK, ClaimType.UNFINISHED_WORK, ClaimType.TASK),
        ("deploy", "deployment", "release", "rollout"),
    )
    return _answer(
        "identify_deployment_blocker",
        "Identify an unresolved deployment blocker.",
        claims,
        conflicted,
        missing_explanation="No unresolved deployment blocker is documented.",
    )


def _q_rollback(ctx: Any, conflicted: set[uuid.UUID]) -> dict[str, Any]:
    claims = _with_keywords(
        _approved_claims(ctx, ClaimType.OPERATIONAL_PROCEDURE, ClaimType.RISK),
        ("rollback", "roll back", "revert", "restore", "back out", "backout"),
    )
    return _answer(
        "locate_rollback_procedure",
        "Locate the rollback procedure.",
        claims,
        conflicted,
        missing_explanation="No rollback procedure is documented.",
    )


def _q_owner(ctx: Any, conflicted: set[uuid.UUID]) -> dict[str, Any]:
    claims = _approved_claims(ctx, ClaimType.OWNERSHIP, ClaimType.RESPONSIBILITY)
    return _answer(
        "identify_owner",
        "Identify who owns or is responsible for a critical part of the project.",
        claims,
        conflicted,
        missing_explanation="No ownership or responsibility statement is approved.",
    )


def _q_current_status(ctx: Any, conflicted: set[uuid.UUID]) -> dict[str, Any]:
    claims = _approved_claims(ctx, ClaimType.STATUS, ClaimType.PROCESS)
    return _answer(
        "describe_current_status",
        "Describe the project's current status.",
        claims,
        conflicted,
        missing_explanation="No approved statement describes the project's current status.",
    )


def _q_open_question(ctx: Any, conflicted: set[uuid.UUID]) -> dict[str, Any]:
    claims = _approved_claims(ctx, ClaimType.OPEN_QUESTION)
    return _answer(
        "find_open_question",
        "Find an unresolved question the successor should answer.",
        claims,
        conflicted,
        missing_explanation="No unresolved question is documented.",
    )


_QUESTIONS = (
    _q_repository,
    _q_external_service,
    _q_retry_policy,
    _q_deployment_blocker,
    _q_rollback,
    _q_owner,
    _q_current_status,
    _q_open_question,
)


__all__ = ["ContinuityService", "EXERCISE_DATASET_VERSION"]
