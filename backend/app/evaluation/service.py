"""Evaluation runner and run comparison (Phase 5 §9).

The service loads the *observations* (claims, evidence, conflicts, staleness,
readiness, handover statements) from PostgreSQL, applies the pure metrics and
persists a reproducible :class:`~app.models.phase5.EvaluationRun`. Repeated runs
on unchanged data produce identical metrics; runs on changed data can be
compared to detect regressions.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.evaluation.ground_truth import GROUND_TRUTH, GroundTruthDataset
from app.evaluation.metrics import (
    HEADLINE_METRICS,
    INVERTED_METRICS,
    ClaimObservation,
    Observations,
    compute_all,
)
from app.models.claim import Claim
from app.models.conflict import Conflict, ConflictClaim
from app.models.enums import (
    ClaimStatus,
    ConflictStatus,
    EvaluationKind,
    FreshnessStatus,
    StatementType,
)
from app.models.evidence import Evidence
from app.models.handover import Handover, HandoverVersion
from app.models.phase5 import EvaluationRun, ReadinessEvaluation
from app.models.source import Source
from app.models.verification import Verification
from app.services import audit_service
from app.services.handover_service import HandoverService

logger = logging.getLogger("continuum.evaluation")

_APPROVED = ClaimStatus.VERIFIED

#: A metric movement smaller than this is treated as noise, not a regression.
REGRESSION_TOLERANCE = 0.0001


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationService:
    """Runs, persists and compares reproducible evaluations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Observations
    # ------------------------------------------------------------------
    def observe(self, project_id: uuid.UUID) -> Observations:
        claims = list(
            self.db.execute(select(Claim).where(Claim.project_id == project_id))
            .scalars()
            .all()
        )
        verdicts = self._latest_verdicts([claim.id for claim in claims])
        claim_ids = [claim.id for claim in claims]

        handover = HandoverService(self.db)
        visible_index = handover.evidence_index(claim_ids)
        all_index = handover.evidence_index(claim_ids, include_restricted=True)

        observations = Observations(
            claims=[
                ClaimObservation(
                    id=str(claim.id),
                    text=claim.text,
                    claim_type=claim.claim_type.value,
                    entity=claim.entity,
                    status=claim.status.value,
                    approved=claim.status == _APPROVED,
                    critical=bool(claim.critical),
                    evidence_sources=sorted(
                        {item["source_name"] for item in (all_index.get(claim.id) or [])}
                    ),
                    verdict=verdicts.get(claim.id),
                )
                for claim in claims
            ],
            conflict_pairs=self._conflict_pairs(project_id),
            stale_sources=self._stale_sources(project_id),
            visible_evidence_sources=sorted(
                {item["source_name"] for refs in visible_index.values() for item in refs}
            ),
            all_evidence_sources=sorted(
                {item["source_name"] for refs in all_index.values() for item in refs}
            ),
            readiness_requirements=self._readiness_requirements(project_id),
            handover_statements=self._handover_statements(project_id),
        )
        return observations

    def _latest_verdicts(self, claim_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not claim_ids:
            return {}
        rows = self.db.execute(
            select(Verification.claim_id, Verification.verdict, Verification.created_at)
            .where(Verification.claim_id.in_(claim_ids))
            .order_by(Verification.created_at.asc())
        ).all()
        latest: dict[uuid.UUID, str] = {}
        for claim_id, verdict, _created in rows:
            latest[claim_id] = (
                verdict.value if hasattr(verdict, "value") else str(verdict)
            )
        return latest

    def _conflict_pairs(self, project_id: uuid.UUID) -> list[frozenset[str]]:
        rows = self.db.execute(
            select(ConflictClaim.conflict_id, ConflictClaim.claim_id)
            .join(Conflict, Conflict.id == ConflictClaim.conflict_id)
            .where(
                Conflict.project_id == project_id,
                Conflict.kind == "value_disagreement",
            )
        ).all()
        grouped: dict[uuid.UUID, list[str]] = {}
        for conflict_id, claim_id in rows:
            grouped.setdefault(conflict_id, []).append(str(claim_id))
        pairs: list[frozenset[str]] = []
        for members in grouped.values():
            if len(members) < 2:
                continue
            pairs.append(frozenset(members))
        return pairs

    def _stale_sources(self, project_id: uuid.UUID) -> list[str]:
        rows = self.db.execute(
            select(Source.source_name).where(
                Source.project_id == project_id,
                Source.freshness.in_(
                    [
                        FreshnessStatus.POTENTIALLY_STALE,
                        FreshnessStatus.CONTRADICTED_BY_NEWER_EVIDENCE,
                    ]
                ),
            )
        ).all()
        return sorted({name for (name,) in rows})

    def _readiness_requirements(self, project_id: uuid.UUID) -> dict[str, str]:
        evaluation = self.db.execute(
            select(ReadinessEvaluation)
            .where(ReadinessEvaluation.project_id == project_id)
            .order_by(ReadinessEvaluation.created_at.desc(), ReadinessEvaluation.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if evaluation is None:
            return {}
        return {
            str(item.get("requirement_id")): str(item.get("completion"))
            for item in (evaluation.requirements or [])
            if isinstance(item, dict)
        }

    def _handover_statements(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        version = self.db.execute(
            select(HandoverVersion)
            .join(Handover, Handover.id == HandoverVersion.handover_id)
            .where(Handover.project_id == project_id)
            .order_by(HandoverVersion.created_at.desc(), HandoverVersion.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if version is None:
            return []
        statements: list[dict[str, Any]] = []
        for section in version.structured_content or []:
            if not isinstance(section, dict) or section.get("removed"):
                continue
            for statement in section.get("statements") or []:
                if not isinstance(statement, dict):
                    continue
                statements.append(
                    {
                        "unsupported": bool(statement.get("unsupported")),
                        "evidence_backed": (
                            str(statement.get("statement_type"))
                            == StatementType.ESTABLISHED_FACT.value
                        ),
                    }
                )
        return statements

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------
    def run_metrics(
        self,
        project_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        dataset: GroundTruthDataset = GROUND_TRUTH,
        model_version: str | None = None,
    ) -> EvaluationRun:
        observations = self.observe(project_id)
        full = compute_all(observations, dataset)

        metrics: dict[str, Any] = {
            name: full[name]["value"]
            for name in (*HEADLINE_METRICS, *INVERTED_METRICS)
            if isinstance(full.get(name), dict) and "value" in full[name]
        }
        metrics["H_permission_leakage"] = full["H_permission_leakage"]["value"]
        metrics["permission_leakage_passed"] = bool(
            full["H_permission_leakage"].get("passed")
        )

        failures: list[dict[str, Any]] = []
        for name, result in full.items():
            if not isinstance(result, dict):
                continue
            if result.get("undefined"):
                failures.append(
                    {"metric": name, "reason": "no data to evaluate (denominator was zero)"}
                )
        leakage = full["H_permission_leakage"]
        if not leakage.get("passed", True):
            failures.append(
                {
                    "metric": "H_permission_leakage",
                    "reason": "a restricted source was exposed or missing where expected",
                    "checks": leakage.get("checks", []),
                }
            )

        run = EvaluationRun(
            project_id=project_id,
            kind=EvaluationKind.METRICS,
            dataset_version=dataset.version,
            model_version=model_version,
            configuration={
                "evaluation_framework": "continuum-eval-v1",
                "observations": {
                    "claims": len(observations.claims),
                    "conflict_pairs": len(observations.conflict_pairs),
                    "stale_sources": len(observations.stale_sources),
                    "handover_statements": len(observations.handover_statements),
                },
            },
            metrics=metrics,
            failures=failures,
            report=full,
            created_by_id=user_id,
        )
        self.db.add(run)
        self.db.flush()
        audit_service.record(
            self.db,
            action="evaluation_metrics_run",
            user_id=user_id,
            workspace_id=workspace_id,
            resource_type="evaluation_run",
            resource_id=run.id,
            metadata={
                "project_id": str(project_id),
                "dataset_version": dataset.version,
                "metrics": metrics,
            },
        )
        return run

    def list_runs(
        self,
        project_id: uuid.UUID,
        *,
        kind: EvaluationKind | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[EvaluationRun], int]:
        filters = [EvaluationRun.project_id == project_id]
        if kind is not None:
            filters.append(EvaluationRun.kind == kind)
        total = int(
            self.db.execute(
                select(func.count()).select_from(EvaluationRun).where(*filters)
            ).scalar_one()
        )
        rows = list(
            self.db.execute(
                select(EvaluationRun)
                .where(*filters)
                .order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            ).scalars().all()
        )
        return rows, total

    def get_run(self, project_id: uuid.UUID, run_id: uuid.UUID) -> EvaluationRun:
        run = self.db.get(EvaluationRun, run_id)
        if run is None or run.project_id != project_id:
            raise NotFoundError("Evaluation run not found.")
        return run

    def latest_run(
        self, project_id: uuid.UUID, *, kind: EvaluationKind | None = None
    ) -> EvaluationRun | None:
        filters = [EvaluationRun.project_id == project_id]
        if kind is not None:
            filters.append(EvaluationRun.kind == kind)
        return self.db.execute(
            select(EvaluationRun)
            .where(*filters)
            .order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------
    def compare(
        self,
        project_id: uuid.UUID,
        *,
        base_run_id: uuid.UUID,
        candidate_run_id: uuid.UUID,
    ) -> dict[str, Any]:
        base = self.get_run(project_id, base_run_id)
        candidate = self.get_run(project_id, candidate_run_id)
        if base.kind != candidate.kind:
            raise ValidationAppError(
                "Only evaluation runs of the same kind can be compared.",
                code="incomparable_runs",
            )
        if base.dataset_version != candidate.dataset_version:
            raise ValidationAppError(
                "The two runs use different dataset versions and are not comparable.",
                code="dataset_version_mismatch",
            )

        base_metrics = dict(base.metrics or {})
        candidate_metrics = dict(candidate.metrics or {})
        names = sorted(set(base_metrics) | set(candidate_metrics))

        deltas: list[dict[str, Any]] = []
        regressions: list[dict[str, Any]] = []
        improvements: list[dict[str, Any]] = []
        for name in names:
            before = base_metrics.get(name)
            after = candidate_metrics.get(name)
            if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
                if before != after:
                    deltas.append({"metric": name, "before": before, "after": after})
                continue
            delta = round(float(after) - float(before), 4)
            entry = {"metric": name, "before": before, "after": after, "delta": delta}
            deltas.append(entry)
            if name in INVERTED_METRICS:
                if delta > REGRESSION_TOLERANCE:
                    regressions.append(entry)
                elif delta < -REGRESSION_TOLERANCE:
                    improvements.append(entry)
            elif delta < -REGRESSION_TOLERANCE:
                regressions.append(entry)
            elif delta > REGRESSION_TOLERANCE:
                improvements.append(entry)

        return {
            "project_id": str(project_id),
            "base_run_id": str(base.id),
            "candidate_run_id": str(candidate.id),
            "dataset_version": candidate.dataset_version,
            "deltas": deltas,
            "regressions": regressions,
            "improvements": improvements,
            "regression_count": len(regressions),
            "improvement_count": len(improvements),
        }


__all__ = ["EvaluationService", "REGRESSION_TOLERANCE"]
