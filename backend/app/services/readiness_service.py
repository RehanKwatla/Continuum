"""Deterministic Handover Readiness Engine (Phase 5 §2–§3).

The engine answers one question: *given only the knowledge a reviewer has
approved, is this handover complete, trustworthy and actionable?*

It is deterministic by construction:

* requirements are declared in :mod:`app.services.readiness_catalog`;
* each requirement's completion is derived from the approved claims, their
  evidence and the open conflicts — never from an LLM judgement;
* the score is a pure function of those completions and the configured weights;
* the entire result (weights, completions, reasons and the exact claim
  revisions used) is persisted so a score can always be re-derived and audited.

The engine never claims a project is ready merely because a handover document
exists, and it never hides a blocker behind a high average.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.models.claim import Claim
from app.models.conflict import Conflict, ConflictClaim
from app.models.enums import (
    COMPLETION_VALUES,
    CRITICALITY_WEIGHTS,
    ClaimStatus,
    ClaimType,
    ConflictStatus,
    HandoverLifecycleStatus,
    ReadinessBand,
    ReadinessDimension,
    RequirementCompletion,
    RequirementCriticality,
)
from app.models.evidence import Evidence
from app.models.handover import Handover, HandoverVersion
from app.models.phase5 import ReadinessEvaluation
from app.models.source import Source
from app.services import audit_service
from app.services.readiness_catalog import (
    DEFAULT_BANDS,
    DIMENSION_LABELS,
    REQUIREMENTS_BY_DIMENSION,
    SCORING_FORMULA,
    RequirementSpec,
    band_for_score,
    default_weights,
)

logger = logging.getLogger("continuum.readiness")

_APPROVED = ClaimStatus.VERIFIED


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class RequirementResult:
    """The deterministic outcome of evaluating one requirement."""

    requirement_id: str
    dimension: str
    description: str
    criticality: str
    completion: RequirementCompletion
    supporting_claim_ids: list[str] = field(default_factory=list)
    supporting_source_ids: list[str] = field(default_factory=list)
    missing_information: str = ""
    evaluation_reason: str = ""
    suggested_resolution: str = ""
    gap_category: str = "other"

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "dimension": self.dimension,
            "description": self.description,
            "criticality": self.criticality,
            "completion": self.completion.value,
            "supporting_claim_ids": self.supporting_claim_ids,
            "supporting_source_ids": self.supporting_source_ids,
            "missing_information": self.missing_information,
            "evaluation_reason": self.evaluation_reason,
            "suggested_resolution": self.suggested_resolution,
            "gap_category": self.gap_category,
        }


@dataclass
class ReadinessResult:
    overall_score: float
    band: str
    dimension_scores: dict[str, dict[str, Any]]
    requirements: list[RequirementResult]
    blockers: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    weights: dict[str, float]
    claim_revisions: dict[str, int]


# ---------------------------------------------------------------------------
# Evaluation context
# ---------------------------------------------------------------------------
@dataclass
class ReadinessContext:
    """Everything the deterministic evaluators are allowed to look at."""

    project_id: uuid.UUID
    approved_claims: list[Claim]
    approved_by_type: dict[ClaimType, list[Claim]]
    unapproved_by_type: dict[ClaimType, list[Claim]]
    evidence_counts: dict[uuid.UUID, int]
    source_types_present: set[str]
    source_ids_by_type: dict[str, list[str]]
    conflicted_claim_ids: set[uuid.UUID]
    critical_conflicts: list[Conflict]
    open_conflicts: list[Conflict]

    @property
    def approved_total(self) -> int:
        return len(self.approved_claims)


def build_context(db: Session, project_id: uuid.UUID) -> ReadinessContext:
    """Load the approved knowledge, evidence and conflicts for one project."""
    claims = list(
        db.execute(select(Claim).where(Claim.project_id == project_id)).scalars().all()
    )
    approved = [c for c in claims if c.status == _APPROVED]
    approved_by_type: dict[ClaimType, list[Claim]] = {}
    unapproved_by_type: dict[ClaimType, list[Claim]] = {}
    for claim in approved:
        approved_by_type.setdefault(claim.claim_type, []).append(claim)
    for claim in claims:
        if claim.status != _APPROVED:
            unapproved_by_type.setdefault(claim.claim_type, []).append(claim)

    evidence_counts: dict[uuid.UUID, int] = {}
    if approved:
        rows = db.execute(
            select(Evidence.claim_id, func.count())
            .where(Evidence.claim_id.in_([c.id for c in approved]))
            .group_by(Evidence.claim_id)
        ).all()
        evidence_counts = {claim_id: int(count) for claim_id, count in rows}

    source_rows = db.execute(
        select(Source.id, Source.source_type).where(Source.project_id == project_id)
    ).all()
    source_ids_by_type: dict[str, list[str]] = {}
    for source_id, source_type in source_rows:
        source_ids_by_type.setdefault(str(source_type), []).append(str(source_id))
    source_types_present = set(source_ids_by_type)

    open_conflicts = list(
        db.execute(
            select(Conflict).where(
                Conflict.project_id == project_id, Conflict.status == ConflictStatus.OPEN
            )
        ).scalars().all()
    )
    conflicted_claim_ids: set[uuid.UUID] = set()
    critical_conflicts: list[Conflict] = []
    if open_conflicts:
        conflict_ids = [c.id for c in open_conflicts]
        link_rows = db.execute(
            select(ConflictClaim.conflict_id, ConflictClaim.claim_id).where(
                ConflictClaim.conflict_id.in_(conflict_ids)
            )
        ).all()
        critical_claim_ids = {c.id for c in claims if c.critical}
        by_conflict: dict[uuid.UUID, list[uuid.UUID]] = {}
        for conflict_id, claim_id in link_rows:
            conflicted_claim_ids.add(claim_id)
            by_conflict.setdefault(conflict_id, []).append(claim_id)
        for conflict in open_conflicts:
            linked = by_conflict.get(conflict.id, [])
            if any(claim_id in critical_claim_ids for claim_id in linked):
                critical_conflicts.append(conflict)

    return ReadinessContext(
        project_id=project_id,
        approved_claims=approved,
        approved_by_type=approved_by_type,
        unapproved_by_type=unapproved_by_type,
        evidence_counts=evidence_counts,
        source_types_present=source_types_present,
        source_ids_by_type=source_ids_by_type,
        conflicted_claim_ids=conflicted_claim_ids,
        critical_conflicts=critical_conflicts,
        open_conflicts=open_conflicts,
    )


# ---------------------------------------------------------------------------
# Requirement evaluation
# ---------------------------------------------------------------------------
def _claim_matches(claim: Claim, keywords: tuple[str, ...]) -> bool:
    if not keywords:
        return True
    haystack = f"{claim.text} {claim.entity or ''}".lower()
    return any(keyword in haystack for keyword in keywords)


def _candidates(ctx: ReadinessContext, spec: RequirementSpec, *, approved: bool) -> list[Claim]:
    pool = ctx.approved_by_type if approved else ctx.unapproved_by_type
    found: list[Claim] = []
    for claim_type in spec.claim_types:
        for claim in pool.get(claim_type, []):
            if _claim_matches(claim, spec.keywords):
                found.append(claim)
    return found


def _generic_evaluate(spec: RequirementSpec, ctx: ReadinessContext) -> RequirementResult:
    candidates = _candidates(ctx, spec, approved=True)
    with_evidence = [c for c in candidates if ctx.evidence_counts.get(c.id, 0) > 0]
    approved_total = len(candidates)
    evidence_total = len(with_evidence)
    supporting = sorted(str(c.id) for c in candidates)

    # A source-backed requirement (e.g. a connected repository) is satisfied by
    # the source itself: the reference is available even if no claim describes it.
    supporting_sources: list[str] = []
    for source_type in spec.source_types:
        supporting_sources.extend(ctx.source_ids_by_type.get(str(source_type), []))
    source_satisfied = bool(supporting_sources)

    if approved_total == 0 and source_satisfied:
        return RequirementResult(
            requirement_id=spec.requirement_id,
            dimension=spec.dimension.value,
            description=spec.description,
            criticality=spec.criticality.value,
            completion=RequirementCompletion.COMPLETE,
            supporting_source_ids=sorted(supporting_sources),
            evaluation_reason=(
                "Satisfied by an available source reference (type: "
                + ", ".join(str(item) for item in spec.source_types)
                + ")."
            ),
            gap_category=spec.gap_category,
        )

    if approved_total == 0:
        unapproved = _candidates(ctx, spec, approved=False)
        if unapproved:
            return RequirementResult(
                requirement_id=spec.requirement_id,
                dimension=spec.dimension.value,
                description=spec.description,
                criticality=spec.criticality.value,
                completion=RequirementCompletion.UNCERTAIN,
                supporting_claim_ids=sorted(str(c.id) for c in unapproved),
                missing_information=spec.missing_information,
                evaluation_reason=(
                    f"{len(unapproved)} candidate claim(s) exist but are not yet "
                    "approved; unapproved knowledge earns no credit."
                ),
                suggested_resolution=spec.suggested_resolution,
                gap_category=spec.gap_category,
            )
        return RequirementResult(
            requirement_id=spec.requirement_id,
            dimension=spec.dimension.value,
            description=spec.description,
            criticality=spec.criticality.value,
            completion=RequirementCompletion.MISSING,
            missing_information=spec.missing_information,
            evaluation_reason="No approved claim satisfies this requirement.",
            suggested_resolution=spec.suggested_resolution,
            gap_category=spec.gap_category,
        )

    blocked = [c for c in candidates if c.id in ctx.conflicted_claim_ids]
    if blocked:
        return RequirementResult(
            requirement_id=spec.requirement_id,
            dimension=spec.dimension.value,
            description=spec.description,
            criticality=spec.criticality.value,
            completion=RequirementCompletion.BLOCKED,
            supporting_claim_ids=supporting,
            missing_information=spec.missing_information,
            evaluation_reason=(
                f"{len(blocked)} supporting claim(s) are part of an unresolved "
                "conflict and cannot count until it is resolved."
            ),
            suggested_resolution="Resolve the open conflict on the supporting claims.",
            gap_category=spec.gap_category,
        )

    needs_evidence = min(spec.min_approved, evidence_total)
    if approved_total >= spec.min_approved and (
        not spec.require_evidence or needs_evidence >= spec.min_approved
    ):
        return RequirementResult(
            requirement_id=spec.requirement_id,
            dimension=spec.dimension.value,
            description=spec.description,
            criticality=spec.criticality.value,
            completion=RequirementCompletion.COMPLETE,
            supporting_claim_ids=supporting,
            evaluation_reason=(
                f"{approved_total} approved claim(s) satisfy this requirement"
                + (f", {evidence_total} with supporting evidence." if spec.require_evidence else ".")
            ),
            gap_category=spec.gap_category,
        )

    if approved_total >= spec.min_approved:
        reason = (
            f"{approved_total} approved claim(s) are present but only "
            f"{evidence_total} cite supporting evidence (needed {spec.min_approved})."
        )
    else:
        reason = (
            f"Only {approved_total} approved claim(s) are present; "
            f"{spec.min_approved} are needed."
        )
    return RequirementResult(
        requirement_id=spec.requirement_id,
        dimension=spec.dimension.value,
        description=spec.description,
        criticality=spec.criticality.value,
        completion=RequirementCompletion.PARTIAL,
        supporting_claim_ids=supporting,
        missing_information=spec.missing_information,
        evaluation_reason=reason,
        suggested_resolution=spec.suggested_resolution,
        gap_category=spec.gap_category,
    )


def _evaluate_unowned_flagged(spec: RequirementSpec, ctx: ReadinessContext) -> RequirementResult:
    """Responsibilities with no approved owner are flagged, never assumed."""
    responsibilities = _candidates(
        ctx,
        RequirementSpec(
            requirement_id=spec.requirement_id,
            dimension=spec.dimension,
            description=spec.description,
            criticality=spec.criticality,
            claim_types=(ClaimType.RESPONSIBILITY,),
        ),
        approved=True,
    ) + _candidates(
        ctx,
        RequirementSpec(
            requirement_id=spec.requirement_id,
            dimension=spec.dimension,
            description=spec.description,
            criticality=spec.criticality,
            claim_types=(ClaimType.OWNERSHIP,),
        ),
        approved=True,
    )
    ownership_entities = {
        (c.entity or "").strip().lower()
        for c in ctx.approved_by_type.get(ClaimType.OWNERSHIP, [])
        if (c.entity or "").strip()
    }
    unowned = [
        c
        for c in responsibilities
        if c.claim_type == ClaimType.RESPONSIBILITY
        and (c.entity or "").strip().lower() not in ownership_entities
    ]
    if not responsibilities:
        return RequirementResult(
            requirement_id=spec.requirement_id,
            dimension=spec.dimension.value,
            description=spec.description,
            criticality=spec.criticality.value,
            completion=RequirementCompletion.COMPLETE,
            evaluation_reason="No responsibilities are recorded, so nothing is left unowned.",
            gap_category=spec.gap_category,
        )
    if unowned:
        return RequirementResult(
            requirement_id=spec.requirement_id,
            dimension=spec.dimension.value,
            description=spec.description,
            criticality=spec.criticality.value,
            completion=RequirementCompletion.PARTIAL,
            supporting_claim_ids=sorted(str(c.id) for c in unowned),
            missing_information=spec.missing_information,
            evaluation_reason=(
                f"{len(unowned)} approved responsibility statement(s) have no matching "
                "approved ownership statement."
            ),
            suggested_resolution=spec.suggested_resolution,
            gap_category=spec.gap_category,
        )
    return RequirementResult(
        requirement_id=spec.requirement_id,
        dimension=spec.dimension.value,
        description=spec.description,
        criticality=spec.criticality.value,
        completion=RequirementCompletion.COMPLETE,
        supporting_claim_ids=sorted(str(c.id) for c in responsibilities),
        evaluation_reason="Every recorded responsibility has a matching ownership statement.",
        gap_category=spec.gap_category,
    )


def _evaluate_evidence_backed(spec: RequirementSpec, ctx: ReadinessContext) -> RequirementResult:
    """Every approved ownership statement must cite evidence."""
    candidates = _candidates(ctx, spec, approved=True)
    if not candidates:
        return RequirementResult(
            requirement_id=spec.requirement_id,
            dimension=spec.dimension.value,
            description=spec.description,
            criticality=spec.criticality.value,
            completion=RequirementCompletion.MISSING,
            missing_information=spec.missing_information,
            evaluation_reason="No approved ownership statement exists to check.",
            suggested_resolution=spec.suggested_resolution,
            gap_category=spec.gap_category,
        )
    without = [c for c in candidates if ctx.evidence_counts.get(c.id, 0) == 0]
    supporting = sorted(str(c.id) for c in candidates)
    if without:
        return RequirementResult(
            requirement_id=spec.requirement_id,
            dimension=spec.dimension.value,
            description=spec.description,
            criticality=spec.criticality.value,
            completion=RequirementCompletion.PARTIAL,
            supporting_claim_ids=sorted(str(c.id) for c in without),
            missing_information=spec.missing_information,
            evaluation_reason=(
                f"{len(without)} of {len(candidates)} approved ownership statement(s) "
                "cite no supporting evidence."
            ),
            suggested_resolution=spec.suggested_resolution,
            gap_category=spec.gap_category,
        )
    return RequirementResult(
        requirement_id=spec.requirement_id,
        dimension=spec.dimension.value,
        description=spec.description,
        criticality=spec.criticality.value,
        completion=RequirementCompletion.COMPLETE,
        supporting_claim_ids=supporting,
        evaluation_reason="All approved ownership statements cite supporting evidence.",
        gap_category=spec.gap_category,
    )


_SPECIAL_EVALUATORS: dict[str, Callable[[RequirementSpec, ReadinessContext], RequirementResult]] = {
    "owner.unowned_flagged": _evaluate_unowned_flagged,
    "owner.evidence_backed": _evaluate_evidence_backed,
}


def evaluate_requirement(spec: RequirementSpec, ctx: ReadinessContext) -> RequirementResult:
    special = _SPECIAL_EVALUATORS.get(spec.requirement_id)
    if special is not None:
        return special(spec, ctx)
    return _generic_evaluate(spec, ctx)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def normalise_weights(raw: dict[str, float] | None) -> dict[ReadinessDimension, float]:
    """Validate and normalise configurable dimension weights (must total 100)."""
    if raw is None:
        return dict(_DEFAULT_DIMENSION_WEIGHTS)
    weights: dict[ReadinessDimension, float] = {}
    for key, value in raw.items():
        try:
            dimension = ReadinessDimension(str(key))
        except ValueError as exc:  # noqa: PERF203
            raise ValidationAppError(
                f"Unknown readiness dimension in weights: '{key}'.",
                code="invalid_weights",
            ) from exc
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationAppError(
                f"Weight for '{key}' must be a number.",
                code="invalid_weights",
            ) from exc
        if number < 0:
            raise ValidationAppError(
                f"Weight for '{key}' must not be negative.",
                code="invalid_weights",
            )
        weights[dimension] = number
    missing = [d.value for d in ReadinessDimension if d not in weights]
    if missing:
        raise ValidationAppError(
            "Weights must be provided for every dimension; missing: " + ", ".join(missing),
            code="invalid_weights",
        )
    total = sum(weights.values())
    if abs(total - 100.0) > 0.5:
        raise ValidationAppError(
            f"Dimension weights must total 100 (received {total:.2f}).",
            code="invalid_weights",
        )
    return weights


_DEFAULT_DIMENSION_WEIGHTS = {
    ReadinessDimension(key): value for key, value in default_weights().items()
}


def _dimension_score(results: list[RequirementResult]) -> tuple[float, float]:
    """Return ``(score_0_100, total_criticality_weight)`` for a dimension."""
    total_weight = 0.0
    earned = 0.0
    for result in results:
        criticality = RequirementCriticality(result.criticality)
        weight = CRITICALITY_WEIGHTS[criticality]
        total_weight += weight
        earned += weight * COMPLETION_VALUES[result.completion]
    if total_weight == 0:
        return 0.0, 0.0
    return 100.0 * earned / total_weight, total_weight


class ReadinessService:
    """Evaluates and persists deterministic readiness assessments."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -- reads -----------------------------------------------------------
    def latest(self, project_id: uuid.UUID) -> ReadinessEvaluation | None:
        return self.db.execute(
            select(ReadinessEvaluation)
            .where(ReadinessEvaluation.project_id == project_id)
            .order_by(ReadinessEvaluation.created_at.desc(), ReadinessEvaluation.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def history(
        self, project_id: uuid.UUID, *, limit: int = 20
    ) -> list[ReadinessEvaluation]:
        return list(
            self.db.execute(
                select(ReadinessEvaluation)
                .where(ReadinessEvaluation.project_id == project_id)
                .order_by(ReadinessEvaluation.created_at.desc(), ReadinessEvaluation.id.desc())
                .limit(limit)
            ).scalars().all()
        )

    def get(self, project_id: uuid.UUID, evaluation_id: uuid.UUID) -> ReadinessEvaluation:
        evaluation = self.db.get(ReadinessEvaluation, evaluation_id)
        if evaluation is None or evaluation.project_id != project_id:
            raise NotFoundError("Readiness evaluation not found.")
        return evaluation

    # -- core ------------------------------------------------------------
    def compute(
        self, ctx: ReadinessContext, *, weights: dict[str, float] | None = None
    ) -> ReadinessResult:
        """Compute a readiness result without persisting anything."""
        resolved_weights = normalise_weights(weights)

        requirements: list[RequirementResult] = []
        dimension_scores: dict[str, dict[str, Any]] = {}
        for dimension in ReadinessDimension:
            specs = REQUIREMENTS_BY_DIMENSION[dimension]
            results = [evaluate_requirement(spec, ctx) for spec in specs]
            requirements.extend(results)
            score, total_weight = _dimension_score(results)
            complete = sum(1 for r in results if r.completion == RequirementCompletion.COMPLETE)
            dimension_scores[dimension.value] = {
                "key": dimension.value,
                "label": DIMENSION_LABELS[dimension],
                "score": round(score, 2),
                "weight": resolved_weights[dimension],
                "requirement_count": len(results),
                "complete_count": complete,
                "criticality_weight": total_weight,
            }

        overall = sum(
            dimension_scores[dimension.value]["score"] * resolved_weights[dimension] / 100.0
            for dimension in ReadinessDimension
        )
        overall = round(overall, 2)

        blockers = self._blockers(requirements, ctx)
        warnings = self._warnings(requirements, ctx)

        claim_revisions = {
            str(claim.id): int(claim.revision_number) for claim in ctx.approved_claims
        }

        return ReadinessResult(
            overall_score=overall,
            band=band_for_score(overall, DEFAULT_BANDS),
            dimension_scores=dimension_scores,
            requirements=requirements,
            blockers=blockers,
            warnings=warnings,
            weights={d.value: resolved_weights[d] for d in ReadinessDimension},
            claim_revisions=claim_revisions,
        )

    def evaluate(
        self,
        project_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        handover_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
        weights: dict[str, float] | None = None,
        source: str = "manual",
    ) -> ReadinessEvaluation:
        """Compute and persist one immutable readiness snapshot."""
        ctx = build_context(self.db, project_id)
        result = self.compute(ctx, weights=weights)

        evaluation = ReadinessEvaluation(
            project_id=project_id,
            handover_id=handover_id,
            run_id=run_id,
            evaluated_by_id=user_id,
            overall_score=result.overall_score,
            band=ReadinessBand(result.band),
            weights=result.weights,
            dimension_scores=result.dimension_scores,
            requirements=[item.to_dict() for item in result.requirements],
            blockers=result.blockers,
            warnings=result.warnings,
            claim_revisions=result.claim_revisions,
            formula=SCORING_FORMULA,
            config={
                "source": source,
                "approved_claim_count": ctx.approved_total,
                "blocker_count": len(result.blockers),
                "warning_count": len(result.warnings),
            },
        )
        self.db.add(evaluation)
        self.db.flush()

        audit_service.record(
            self.db,
            action="readiness_evaluated",
            user_id=user_id,
            workspace_id=workspace_id,
            resource_type="readiness_evaluation",
            resource_id=evaluation.id,
            metadata={
                "project_id": str(project_id),
                "overall_score": result.overall_score,
                "band": result.band,
                "blockers": len(result.blockers),
                "source": source,
            },
        )
        return evaluation

    # -- blockers / warnings ---------------------------------------------
    def _blockers(
        self, requirements: list[RequirementResult], ctx: ReadinessContext
    ) -> list[dict[str, Any]]:
        blockers: list[dict[str, Any]] = []
        for result in requirements:
            criticality = RequirementCriticality(result.criticality)
            if result.completion == RequirementCompletion.BLOCKED:
                blockers.append(
                    {
                        "code": "blocked_requirement",
                        "requirement_id": result.requirement_id,
                        "dimension": result.dimension,
                        "criticality": result.criticality,
                        "message": result.evaluation_reason,
                    }
                )
            elif (
                criticality == RequirementCriticality.CRITICAL
                and result.completion == RequirementCompletion.MISSING
            ):
                blockers.append(
                    {
                        "code": "missing_critical_knowledge",
                        "requirement_id": result.requirement_id,
                        "dimension": result.dimension,
                        "criticality": result.criticality,
                        "message": result.missing_information or result.evaluation_reason,
                    }
                )
        for conflict in ctx.critical_conflicts:
            blockers.append(
                {
                    "code": "unresolved_critical_conflict",
                    "conflict_id": str(conflict.id),
                    "property_key": conflict.property_key,
                    "message": conflict.summary
                    or f"An unresolved conflict affects a critical claim ({conflict.property_key or 'unspecified'}).",
                }
            )
        if ctx.approved_total == 0:
            blockers.append(
                {
                    "code": "no_approved_knowledge",
                    "message": (
                        "No claims have been approved, so no evidence-backed readiness "
                        "statement can be made."
                    ),
                }
            )
        return blockers

    def _warnings(
        self, requirements: list[RequirementResult], ctx: ReadinessContext
    ) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        for result in requirements:
            criticality = RequirementCriticality(result.criticality)
            if result.completion == RequirementCompletion.PARTIAL and criticality in {
                RequirementCriticality.CRITICAL,
                RequirementCriticality.IMPORTANT,
            }:
                warnings.append(
                    {
                        "code": "partially_satisfied_requirement",
                        "requirement_id": result.requirement_id,
                        "dimension": result.dimension,
                        "message": result.evaluation_reason,
                    }
                )
            elif result.completion == RequirementCompletion.UNCERTAIN:
                warnings.append(
                    {
                        "code": "unreviewed_knowledge",
                        "requirement_id": result.requirement_id,
                        "dimension": result.dimension,
                        "message": result.evaluation_reason,
                    }
                )
        critical_ids = {c.id for c in ctx.critical_conflicts}
        for conflict in ctx.open_conflicts:
            if conflict.id in critical_ids:
                continue
            warnings.append(
                {
                    "code": "open_conflict",
                    "conflict_id": str(conflict.id),
                    "property_key": conflict.property_key,
                    "message": conflict.summary
                    or f"An unresolved conflict exists ({conflict.property_key or 'unspecified'}).",
                }
            )
        return warnings


def project_has_published_handover(db: Session, project_id: uuid.UUID) -> uuid.UUID | None:
    """Return the id of the project's latest published handover version, if any."""
    row = db.execute(
        select(Handover.id)
        .join(HandoverVersion, HandoverVersion.handover_id == Handover.id)
        .where(
            Handover.project_id == project_id,
            HandoverVersion.status == HandoverLifecycleStatus.PUBLISHED,
        )
        .order_by(HandoverVersion.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row


__all__ = [
    "ReadinessContext",
    "ReadinessResult",
    "ReadinessService",
    "RequirementResult",
    "build_context",
    "evaluate_requirement",
    "normalise_weights",
    "project_has_published_handover",
]
