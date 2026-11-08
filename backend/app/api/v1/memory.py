"""Project-memory endpoints: reconstruction, review and handover.

Every route resolves project access first (workspace membership is enforced by
:func:`resolve_project_access`), so a source can never reach the workflow without
authorisation. Reads require *viewer*, reconstruction and verification require
*member*, and the two governance actions — approving a claim and resolving a
conflict — require *admin*.

No endpoint invents data. A project that has not been reconstructed returns
``reconstructed: false``; an unconfigured model returns **503** rather than a
fabricated result.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.ai.provider import GeminiProvider, LLMProvider
from app.core.dependencies import CurrentUser, DbSession, resolve_project_access
from app.core.errors import NotConfiguredError, NotFoundError
from app.models.enums import (
    ClaimStatus,
    ClaimType,
    ConflictStatus,
    OpenQuestionStatus,
    ProcessingRunStatus,
    WorkspaceRole,
)
from app.models.processing_run import ProcessingRun
from app.schemas.common import build_page_meta
from app.schemas.memory import (
    ClaimDetail,
    ClaimListResponse,
    ClaimReviewRequest,
    ConflictListResponse,
    ConflictResolveRequest,
    ConflictSummary,
    HandoverRead,
    OpenQuestionListResponse,
    ProcessingRunListResponse,
    ProcessingRunRead,
    ProjectMemoryRead,
    ReconstructRequest,
    UncertaintyResponse,
)
from app.services.memory_service import MemoryService, reconstruct_project

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


def _require_provider(provider: LLMProvider | None) -> LLMProvider:
    if provider is None:
        raise NotConfiguredError(_NOT_CONFIGURED_MESSAGE, code="ai_not_configured")
    return provider


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
# Claims
# ---------------------------------------------------------------------------
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
    summary="Get a claim with its evidence, verifications and history",
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
    _require_provider(provider)
    service = MemoryService(db)
    claim = service.get_claim(project_id, claim_id)
    service.verify_claim(claim, provider=provider)
    return service.claim_detail(claim)


@router.post(
    "/{project_id}/claims/{claim_id}/review",
    response_model=ClaimDetail,
    summary="Human review: approve (Verified) or reject a claim (admins only)",
)
def review_claim(
    project_id: uuid.UUID,
    claim_id: uuid.UUID,
    payload: ClaimReviewRequest,
    user: CurrentUser,
    db: DbSession,
) -> ClaimDetail:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.ADMIN
    )
    service = MemoryService(db)
    claim = service.get_claim(project_id, claim_id)
    service.review_claim(claim, user=user, action=payload.action, note=payload.note)
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


@router.post(
    "/{project_id}/conflicts/{conflict_id}/resolve",
    response_model=ConflictSummary,
    summary="Resolve or dismiss a conflict (admins only)",
)
def resolve_conflict(
    project_id: uuid.UUID,
    conflict_id: uuid.UUID,
    payload: ConflictResolveRequest,
    user: CurrentUser,
    db: DbSession,
) -> ConflictSummary:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.ADMIN
    )
    service = MemoryService(db)
    conflict = service.get_conflict(project_id, conflict_id)
    service.resolve_conflict(
        conflict,
        user=user,
        action=payload.action,
        note=payload.note,
        chosen_claim_id=payload.chosen_claim_id,
    )
    return service.conflict_summary(conflict)


# ---------------------------------------------------------------------------
# Open questions, uncertainty and handover
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


@router.post(
    "/{project_id}/handover/generate",
    response_model=HandoverRead,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a handover from approved claims only",
)
def generate_handover(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    provider: ProviderDep,
) -> HandoverRead:
    project, _ = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    _require_provider(provider)
    document = MemoryService(db).generate_handover(project, user=user, provider=provider)
    return HandoverRead.model_validate(document)


@router.get(
    "/{project_id}/handover",
    response_model=HandoverRead,
    summary="Get the most recent generated handover",
)
def get_handover(project_id: uuid.UUID, user: CurrentUser, db: DbSession) -> HandoverRead:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    document = MemoryService(db).latest_handover(project_id)
    if document is None:
        raise NotFoundError("No handover has been generated for this project yet.")
    return HandoverRead.model_validate(document)


__all__ = ["router", "get_llm_provider"]
