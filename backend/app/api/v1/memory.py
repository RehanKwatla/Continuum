"""Project-memory endpoints: reconstruction, review and conflicts.

Every route resolves project access first (workspace membership is enforced by
:func:`resolve_project_access`), so a source can never reach the workflow without
authorisation. Reads require *viewer*, reconstruction and model verification
require *member*, and the human governance actions — reviewing, approving,
editing or rejecting a claim, and resolving a conflict — require *admin*.

Phase 4 splits the two things that used to be conflated:

* **AI verification** is an *evidence assessment* produced by the model
  (``POST /claims/{id}/verify``). It can never approve anything.
* **Human approval** is an explicit reviewer decision recorded against one exact
  claim revision (``POST /claims/{id}/review`` and the dedicated
  ``/approve``, ``/reject``, ``/request-clarification`` actions).

No endpoint invents data. A project that has not been reconstructed returns
``reconstructed: false``; an unconfigured model returns **503** rather than a
fabricated result.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.ai.provider import GeminiProvider, LLMProvider
from app.core.dependencies import CurrentUser, DbSession, resolve_project_access
from app.core.errors import NotConfiguredError
from app.models.enums import (
    AccessLabel,
    ClaimStatus,
    ClaimType,
    ConflictStatus,
    FreshnessStatus,
    OpenQuestionStatus,
    ProcessingRunStatus,
    WorkspaceRole,
)
from app.models.claim import Claim
from app.models.conflict import Conflict, ConflictClaim
from app.models.processing_run import ProcessingRun
from app.models.verification import Verification
from app.schemas.common import build_page_meta
from app.schemas.memory import (
    ClaimDetail,
    ClaimListResponse,
    ConflictListResponse,
    OpenQuestionListResponse,
    ProcessingRunListResponse,
    ProcessingRunRead,
    ProjectMemoryRead,
    ReconstructRequest,
    UncertaintyResponse,
)
from app.schemas.phase4 import (
    ClaimActionRequest,
    ClaimDecisionRequest,
    ClaimEditRequest,
    ConflictDetail,
    ConflictResolutionRequest,
    ReviewQueueItem,
    ReviewQueueResponse,
)
from app.services import claim_state_machine as machine
from app.services.conflict_resolution import ConflictCentreService
from app.services.memory_service import MemoryService, reconstruct_project
from app.services.review_service import ReviewService, statuses_for_filter

router = APIRouter(prefix="/projects", tags=["memory"])


def get_llm_provider() -> LLMProvider | None:
    """Return the configured model provider, or ``None`` if it is unconfigured.

    Returning ``None`` (instead of raising) lets the reconstruction endpoint
    record an auditable *failed* run before reporting HTTP 503.
    """
    provider = GeminiProvider()
    return provider if provider.configured else None


ProviderDep = Annotated[LLMProvider | None, Depends(get_llm_provider)]

_NOT_CONFIGURED_MESSAGE = (
    "The intelligence layer is not configured. Set GEMINI_API_KEY on the server."
)


def require_provider(provider: LLMProvider | None) -> LLMProvider:
    """Reject a request that needs the model when none is configured (503)."""
    if provider is None:
        raise NotConfiguredError(_NOT_CONFIGURED_MESSAGE, code="ai_not_configured")
    return provider


def _require_reviewer(
    db: DbSession, *, project_id: uuid.UUID, user: CurrentUser
) -> WorkspaceRole:
    """Assert the caller may record a human decision and return their role.

    The frontend hides actions a user may not take, but that is cosmetic: the
    authority check lives here, and the review service re-checks the role before
    it writes anything.
    """
    _, role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.ADMIN
    )
    return role


# ---------------------------------------------------------------------------
# Reconstruction and memory overview
# ---------------------------------------------------------------------------
@router.post(
    "/{project_id}/memory/reconstruct",
    response_model=ProcessingRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Run the project-memory reconstruction workflow",
)
def reconstruct_project_memory(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    provider: ProviderDep,
    payload: ReconstructRequest | None = None,
) -> ProcessingRunRead:
    project, _ = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )

    if provider is None:
        now = datetime.now(timezone.utc)
        run = ProcessingRun(
            project_id=project.id,
            requested_by_id=user.id,
            status=ProcessingRunStatus.FAILED,
            error_message=_NOT_CONFIGURED_MESSAGE,
            started_at=now,
            finished_at=now,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        raise NotConfiguredError(_NOT_CONFIGURED_MESSAGE, code="ai_not_configured")

    run, _state = reconstruct_project(
        db,
        project=project,
        user=user,
        provider=provider,
        source_ids=payload.source_ids if payload else None,
    )
    return ProcessingRunRead.model_validate(run)


@router.get(
    "/{project_id}/memory",
    response_model=ProjectMemoryRead,
    summary="Get the reconstructed project memory overview",
)
def get_project_memory(
    project_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ProjectMemoryRead:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    return MemoryService(db).memory_overview(project_id)


@router.get(
    "/{project_id}/processing-runs",
    response_model=ProcessingRunListResponse,
    summary="List reconstruction runs for a project",
)
def list_processing_runs(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ProcessingRunListResponse:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    items, total = MemoryService(db).list_runs(project_id, page=page, page_size=page_size)
    return ProcessingRunListResponse(items=items, meta=build_page_meta(total, page, page_size))


# ---------------------------------------------------------------------------
# Human review queue (§3)
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/review-queue",
    response_model=ReviewQueueResponse,
    summary="List claims for human review with evidence and staleness indicators",
)
def review_queue(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description=(
            "all | pending | supported | uncertain | conflict | critical | resolved "
            "| approved | rejected | clarification"
        ),
    ),
    critical: bool | None = None,
    order: str = Query(default="recent", pattern="^(critical|recent|oldest|verification)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ReviewQueueResponse:
    resolve_project_access(db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER)
    review = ReviewService(db)

    query = select(Claim).where(Claim.project_id == project_id)
    filter_name = status_filter.casefold() if status_filter else None
    if filter_name == "critical":
        # "Critical" is not a status: it filters on the criticality flag.
        query = query.where(Claim.critical.is_(True))
    else:
        statuses = statuses_for_filter(filter_name)
        if statuses:
            query = query.where(Claim.status.in_(statuses))
    if critical is not None:
        query = query.where(Claim.critical == critical)

    count = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)

    if order == "critical":
        query = query.order_by(Claim.critical.desc(), Claim.created_at.desc())
    elif order == "oldest":
        query = query.order_by(Claim.created_at.asc())
    elif order == "verification":
        query = query.order_by(Claim.status.asc(), Claim.created_at.desc())
    else:
        query = query.order_by(Claim.created_at.desc())

    claims = list(db.scalars(query.limit(page_size).offset((page - 1) * page_size)).all())

    items: list[ReviewQueueItem] = []
    for claim in claims:
        evidence_rows = review.accessible_evidence(claim.id)
        accessible = [
            (evidence, source)
            for evidence, source in evidence_rows
            if source.access_label is not AccessLabel.RESTRICTED
        ]
        latest = db.scalar(
            select(Verification)
            .where(Verification.claim_id == claim.id)
            .order_by(Verification.created_at.desc())
            .limit(1)
        )
        conflict_statuses = db.scalars(
            select(Conflict.status)
            .join(ConflictClaim, ConflictClaim.conflict_id == Conflict.id)
            .where(ConflictClaim.claim_id == claim.id)
        ).all()
        if ConflictStatus.OPEN in conflict_statuses:
            conflict_status = "open"
        elif conflict_statuses:
            conflict_status = "resolved"
        else:
            conflict_status = "clear"
        stale = any(source.freshness is not FreshnessStatus.CURRENT for _, source in accessible)
        items.append(
            ReviewQueueItem(
                id=claim.id,
                text=claim.text,
                category=claim.claim_type,
                critical=claim.critical,
                ai_verdict=latest.verdict.value if latest else None,
                evidence_count=len(accessible),
                source_references=[
                    f"{source.source_name}"
                    + (f" · {evidence.source_location}" if evidence.source_location else "")
                    for evidence, source in accessible
                ],
                conflict_status=conflict_status,
                stale_warning=stale,
                created_at=claim.created_at,
                # AI verification and human approval are separate columns.
                review_status=machine.review_status_label(claim.status),
                status=claim.status,
                revision_number=claim.revision_number,
            )
        )
    return ReviewQueueResponse(items=items, meta=build_page_meta(count, page, page_size))


# ---------------------------------------------------------------------------
# Claim inspection and human review (§4, §5, §7)
# ---------------------------------------------------------------------------
def _apply_decision(
    db: DbSession,
    claim: Claim,
    *,
    user: CurrentUser,
    role: WorkspaceRole,
    decision: str,
    explanation: str | None,
    request_evidence: bool = False,
) -> None:
    """Route one human decision to the approval engine.

    All four outcomes go through :class:`ReviewService`, which enforces the
    state machine, the evidence requirement, the conflict gate and the
    transaction — never the request body and never the browser.
    """
    service = ReviewService(db)
    if decision == "approve":
        service.approve(claim, user=user, role=role, explanation=explanation)
    elif decision == "reject":
        service.reject(claim, user=user, role=role, explanation=explanation)
    else:
        service.request_clarification(
            claim,
            user=user,
            role=role,
            explanation=explanation,
            request_evidence=request_evidence or decision == "request_evidence",
        )


@router.post(
    "/{project_id}/claims/{claim_id}/review",
    response_model=ClaimDetail,
    summary="Record a human claim decision: approve, reject or request clarification",
)
def review_claim(
    project_id: uuid.UUID,
    claim_id: uuid.UUID,
    payload: ClaimDecisionRequest,
    user: CurrentUser,
    db: DbSession,
) -> ClaimDetail:
    role = _require_reviewer(db, project_id=project_id, user=user)
    service = MemoryService(db)
    claim = service.get_claim(project_id, claim_id)
    _apply_decision(
        db,
        claim,
        user=user,
        role=role,
        decision=payload.decision,
        explanation=payload.explanation,
    )
    return service.claim_detail(claim)


@router.post(
    "/{project_id}/claims/{claim_id}/approve",
    response_model=ClaimDetail,
    summary="Approve a claim (the only path to an approved claim)",
)
def approve_claim(
    project_id: uuid.UUID,
    claim_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    payload: ClaimActionRequest | None = None,
) -> ClaimDetail:
    role = _require_reviewer(db, project_id=project_id, user=user)
    service = MemoryService(db)
    claim = service.get_claim(project_id, claim_id)
    _apply_decision(
        db, claim, user=user, role=role, decision="approve",
        explanation=payload.explanation if payload else None,
    )
    return service.claim_detail(claim)


@router.post(
    "/{project_id}/claims/{claim_id}/reject",
    response_model=ClaimDetail,
    summary="Reject a claim; it can never enter an approved handover",
)
def reject_claim(
    project_id: uuid.UUID,
    claim_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    payload: ClaimActionRequest | None = None,
) -> ClaimDetail:
    role = _require_reviewer(db, project_id=project_id, user=user)
    service = MemoryService(db)
    claim = service.get_claim(project_id, claim_id)
    _apply_decision(
        db, claim, user=user, role=role, decision="reject",
        explanation=payload.explanation if payload else None,
    )
    return service.claim_detail(claim)


@router.post(
    "/{project_id}/claims/{claim_id}/request-clarification",
    response_model=ClaimDetail,
    summary="Ask for clarification or additional evidence before deciding",
)
def request_clarification(
    project_id: uuid.UUID,
    claim_id: uuid.UUID,
    payload: ClaimActionRequest,
    user: CurrentUser,
    db: DbSession,
) -> ClaimDetail:
    role = _require_reviewer(db, project_id=project_id, user=user)
    service = MemoryService(db)
    claim = service.get_claim(project_id, claim_id)
    _apply_decision(
        db,
        claim,
        user=user,
        role=role,
        decision="clarification",
        explanation=payload.explanation,
        request_evidence=payload.request_evidence,
    )
    return service.claim_detail(claim)


@router.post(
    "/{project_id}/claims/{claim_id}/edit",
    response_model=ClaimDetail,
    summary="Correct a claim's statement as a new revision that must be re-verified",
)
def edit_claim(
    project_id: uuid.UUID,
    claim_id: uuid.UUID,
    payload: ClaimEditRequest,
    user: CurrentUser,
    db: DbSession,
) -> ClaimDetail:
    _require_reviewer(db, project_id=project_id, user=user)
    service = MemoryService(db)
    claim = service.get_claim(project_id, claim_id)
    ReviewService(db).edit_claim(
        claim,
        user=user,
        text=payload.text,
        claim_type=payload.claim_type,
        entity=payload.entity,
        note=payload.note,
    )
    return service.claim_detail(claim)


@router.get(
    "/{project_id}/claims",
    response_model=ClaimListResponse,
    summary="Browse extracted claims",
)
def list_claims(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    claim_type: ClaimType | None = Query(default=None, alias="category"),
    claim_status: ClaimStatus | None = Query(default=None, alias="status"),
    critical: bool | None = Query(default=None),
    entity: str | None = Query(default=None, max_length=300),
    search: str | None = Query(default=None, max_length=200),
    order: str = Query(default="recent", pattern="^(recent|oldest|timeline)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ClaimListResponse:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    service = MemoryService(db)
    items, total = service.list_claims(
        project_id,
        claim_type=claim_type,
        status=claim_status,
        critical=critical,
        entity=entity,
        search=search,
        order=order,
        page=page,
        page_size=page_size,
    )
    status_counts, type_counts = service.claim_counts(project_id)
    return ClaimListResponse(
        items=items,
        meta=build_page_meta(total, page, page_size),
        status_counts=status_counts,
        type_counts=type_counts,
    )


@router.get(
    "/{project_id}/claims/{claim_id}",
    response_model=ClaimDetail,
    summary="Get a claim with its evidence, verifications, revisions and history",
)
def get_claim(
    project_id: uuid.UUID, claim_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ClaimDetail:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    service = MemoryService(db)
    return service.claim_detail(service.get_claim(project_id, claim_id))


@router.post(
    "/{project_id}/claims/{claim_id}/verify",
    response_model=ClaimDetail,
    summary="Re-run the Verifier for a claim (never approves it)",
)
def verify_claim(
    project_id: uuid.UUID,
    claim_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    provider: ProviderDep,
) -> ClaimDetail:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    require_provider(provider)
    service = MemoryService(db)
    claim = service.get_claim(project_id, claim_id)
    service.verify_claim(claim, provider=provider)
    return service.claim_detail(claim)


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/conflicts",
    response_model=ConflictListResponse,
    summary="List detected contradictions and ownership changes",
)
def list_conflicts(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    conflict_status: ConflictStatus | None = Query(default=None, alias="status"),
    kind: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ConflictListResponse:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    items, total = MemoryService(db).list_conflicts(
        project_id, status=conflict_status, kind=kind, page=page, page_size=page_size
    )
    return ConflictListResponse(items=items, meta=build_page_meta(total, page, page_size))


@router.get(
    "/{project_id}/conflicts/{conflict_id}",
    response_model=ConflictDetail,
    summary="Inspect a contradiction with the evidence behind both sides",
)
def get_conflict(
    project_id: uuid.UUID, conflict_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ConflictDetail:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    service = MemoryService(db)
    return service.conflict_detail(service.get_conflict(project_id, conflict_id))


@router.post(
    "/{project_id}/conflicts/{conflict_id}/resolve",
    response_model=ConflictDetail,
    summary="Decide a contradiction; both claims and all evidence are preserved",
)
def resolve_conflict(
    project_id: uuid.UUID,
    conflict_id: uuid.UUID,
    payload: ConflictResolutionRequest,
    user: CurrentUser,
    db: DbSession,
) -> ConflictDetail:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.ADMIN
    )
    service = MemoryService(db)
    conflict = service.get_conflict(project_id, conflict_id)
    ConflictCentreService(db).resolve(
        conflict,
        user=user,
        resolution=payload.resolution,
        note=payload.note,
        chosen_claim_id=payload.chosen_claim_id,
    )
    return service.conflict_detail(conflict)


# ---------------------------------------------------------------------------
# Open questions and uncertainty
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/questions",
    response_model=OpenQuestionListResponse,
    summary="List open questions the sources raise but do not answer",
)
def list_questions(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    question_status: OpenQuestionStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> OpenQuestionListResponse:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    items, total = MemoryService(db).list_questions(
        project_id, status=question_status, page=page, page_size=page_size
    )
    return OpenQuestionListResponse(items=items, meta=build_page_meta(total, page, page_size))


@router.get(
    "/{project_id}/uncertainty",
    response_model=UncertaintyResponse,
    summary="Uncertainty centre: unsupported claims, questions and stale sources",
)
def get_uncertainty(
    project_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> UncertaintyResponse:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    return MemoryService(db).uncertainty_centre(project_id)


__all__ = ["router", "get_llm_provider"]
