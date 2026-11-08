"""Versioned handover, export and audit-trail endpoints (Phase 4 §8–§15).

Two governance boundaries are visible here:

* **The Handover Writer never approves claims.** ``POST /handovers/generate``
  runs the writer over the project's *already approved* claims; it cannot widen
  that set, and no endpoint on this router writes to a claim.
* **Every access re-checks permission.** The document is only rendered for a
  caller who is a member of the owning workspace, restricted source text is
  never included in an export, and each export appends an audit entry.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.ai.provider import LLMProvider
from app.api.v1.memory import get_llm_provider, require_provider
from app.core.dependencies import CurrentUser, DbSession, resolve_project_access
from app.core.errors import NotFoundError
from app.models.enums import WorkspaceRole
from app.models.handover import Handover, HandoverVersion
from app.schemas.common import build_page_meta
from app.schemas.phase4 import (
    AuditLogRead,
    AuditTrailResponse,
    HandoverDetail,
    HandoverGenerateRequest,
    HandoverListResponse,
    HandoverPublishRequest,
    HandoverUpdateRequest,
    HandoverVersionRead,
)
from app.services import audit_service
from app.services.handover_service import HandoverService

router = APIRouter(prefix="/projects", tags=["handover"])

ProviderDep = Annotated[LLMProvider | None, Depends(get_llm_provider)]


def _reviewer(db: DbSession, *, project_id: uuid.UUID, user: CurrentUser):
    """Resolve project access at *admin* level; returns ``(project, role)``."""
    return resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.ADMIN
    )


def _require_version(
    service: HandoverService, handover: Handover, version_number: int | None
) -> HandoverVersion:
    version = (
        service.version(handover, version_number)
        if version_number is not None
        else service.current_version(handover)
    )
    if version is None:
        raise NotFoundError("This handover has no such version.")
    return version


# ---------------------------------------------------------------------------
# Generation (§8, §9)
# ---------------------------------------------------------------------------
@router.post(
    "/{project_id}/handovers/generate",
    response_model=HandoverDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a draft handover from the project's approved claims",
)
def generate_handover(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    provider: ProviderDep,
    payload: HandoverGenerateRequest | None = None,
) -> HandoverDetail:
    project, _role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    require_provider(provider)
    service = HandoverService(db)
    handover, _version = service.generate(
        project, user=user, provider=provider, title=payload.title if payload else None
    )
    return service.detail(handover)


# ---------------------------------------------------------------------------
# Reads (§12, §13)
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/handovers",
    response_model=HandoverListResponse,
    summary="List a project's handovers",
)
def list_handovers(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> HandoverListResponse:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    service = HandoverService(db)
    total = service.count(project_id)
    rows = service.list(project_id)[(page - 1) * page_size : page * page_size]
    items = [service.detail(row, include_current=False) for row in rows]
    return HandoverListResponse(items=items, meta=build_page_meta(total, page, page_size))


@router.get(
    "/{project_id}/handovers/{handover_id}",
    response_model=HandoverDetail,
    summary="Get a handover with its current version",
)
def get_handover(
    project_id: uuid.UUID, handover_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> HandoverDetail:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    service = HandoverService(db)
    return service.detail(service.get(project_id, handover_id))


@router.get(
    "/{project_id}/handovers/{handover_id}/versions",
    response_model=list[HandoverVersionRead],
    summary="List every version of a handover (newest first)",
)
def list_versions(
    project_id: uuid.UUID, handover_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[HandoverVersionRead]:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    service = HandoverService(db)
    handover = service.get(project_id, handover_id)
    return [service.version_payload(row) for row in service.versions(handover)]


@router.get(
    "/{project_id}/handovers/{handover_id}/versions/{version_number}",
    response_model=HandoverVersionRead,
    summary="Get one immutable version of a handover",
)
def get_version(
    project_id: uuid.UUID,
    handover_id: uuid.UUID,
    version_number: int,
    user: CurrentUser,
    db: DbSession,
) -> HandoverVersionRead:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    service = HandoverService(db)
    handover = service.get(project_id, handover_id)
    return service.version_payload(_require_version(service, handover, version_number))


# ---------------------------------------------------------------------------
# Editing (§11, §12)
# ---------------------------------------------------------------------------
@router.patch(
    "/{project_id}/handovers/{handover_id}",
    response_model=HandoverVersionRead,
    summary="Edit a handover; the edit is stored as a new version",
)
def edit_handover(
    project_id: uuid.UUID,
    handover_id: uuid.UUID,
    payload: HandoverUpdateRequest,
    user: CurrentUser,
    db: DbSession,
) -> HandoverVersionRead:
    _reviewer(db, project_id=project_id, user=user)
    service = HandoverService(db)
    handover = service.get(project_id, handover_id)
    version = service.save_reviewer_edit(handover, user=user, payload=payload)
    return service.version_payload(version)


# ---------------------------------------------------------------------------
# Lifecycle (§12)
# ---------------------------------------------------------------------------
@router.post(
    "/{project_id}/handovers/{handover_id}/submit",
    response_model=HandoverVersionRead,
    summary="Submit the current draft for review",
)
def submit_handover(
    project_id: uuid.UUID, handover_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> HandoverVersionRead:
    _reviewer(db, project_id=project_id, user=user)
    service = HandoverService(db)
    handover = service.get(project_id, handover_id)
    return service.version_payload(service.submit_for_review(handover, user=user))


@router.post(
    "/{project_id}/handovers/{handover_id}/approve",
    response_model=HandoverVersionRead,
    summary="A reviewer approves the current version",
)
def approve_handover(
    project_id: uuid.UUID,
    handover_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    payload: HandoverPublishRequest | None = None,
) -> HandoverVersionRead:
    _project, role = _reviewer(db, project_id=project_id, user=user)
    service = HandoverService(db)
    handover = service.get(project_id, handover_id)
    version = service.approve(
        handover, user=user, role=role, note=payload.note if payload else None
    )
    return service.version_payload(version)


@router.post(
    "/{project_id}/handovers/{handover_id}/publish",
    response_model=HandoverVersionRead,
    summary="Publish an approved version; published versions are immutable",
)
def publish_handover(
    project_id: uuid.UUID,
    handover_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    payload: HandoverPublishRequest | None = None,
) -> HandoverVersionRead:
    _project, role = _reviewer(db, project_id=project_id, user=user)
    service = HandoverService(db)
    handover = service.get(project_id, handover_id)
    version = service.publish(
        handover, user=user, role=role, note=payload.note if payload else None
    )
    return service.version_payload(version)


@router.post(
    "/{project_id}/handovers/{handover_id}/archive",
    response_model=HandoverDetail,
    summary="Archive a handover without deleting its history",
)
def archive_handover(
    project_id: uuid.UUID, handover_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> HandoverDetail:
    _reviewer(db, project_id=project_id, user=user)
    service = HandoverService(db)
    handover = service.get(project_id, handover_id)
    return service.detail(service.archive(handover, user=user))


# ---------------------------------------------------------------------------
# Export (§14)
# ---------------------------------------------------------------------------
def _export_payload(
    db: DbSession,
    *,
    project_id: uuid.UUID,
    handover_id: uuid.UUID,
    user: CurrentUser,
    version_number: int | None,
):
    """Re-check permission on every export and load the exact version."""
    project, _role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    service = HandoverService(db)
    handover = service.get(project_id, handover_id)
    version = _require_version(service, handover, version_number)
    return project, service, handover, version


@router.get(
    "/{project_id}/handovers/{handover_id}/export.md",
    summary="Export a handover version as Markdown",
    response_class=Response,
)
def export_markdown(
    project_id: uuid.UUID,
    handover_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    version: int | None = Query(default=None, ge=1),
) -> Response:
    project, service, handover, row = _export_payload(
        db, project_id=project_id, handover_id=handover_id, user=user, version_number=version
    )
    body = service.render_markdown(handover, row, project=project)
    audit_service.record(
        db,
        action="handover_exported",
        user_id=user.id,
        workspace_id=project.workspace_id,
        resource_type="handover_version",
        resource_id=row.id,
        metadata={
            "project_id": str(project.id),
            "format": "markdown",
            "version_number": row.version_number,
        },
    )
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="handover-{handover.id}-v{row.version_number}.md"'
            )
        },
    )


@router.get(
    "/{project_id}/handovers/{handover_id}/export.pdf",
    summary="Export a handover version as PDF",
    response_class=Response,
)
def export_pdf(
    project_id: uuid.UUID,
    handover_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    version: int | None = Query(default=None, ge=1),
) -> Response:
    project, service, handover, row = _export_payload(
        db, project_id=project_id, handover_id=handover_id, user=user, version_number=version
    )
    payload = service.render_pdf(handover, row, project=project)
    audit_service.record(
        db,
        action="handover_exported",
        user_id=user.id,
        workspace_id=project.workspace_id,
        resource_type="handover_version",
        resource_id=row.id,
        metadata={
            "project_id": str(project.id),
            "format": "pdf",
            "version_number": row.version_number,
        },
    )
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="handover-{handover.id}-v{row.version_number}.pdf"'
            )
        },
    )


# ---------------------------------------------------------------------------
# Audit trail (§15)
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/audit",
    response_model=AuditTrailResponse,
    summary="The project's immutable review, approval and handover history",
)
def project_audit(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    action: str | None = Query(
        default=None, description="Comma-separated audit action names to filter on."
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> AuditTrailResponse:
    project, _role = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    actions = [item.strip() for item in action.split(",") if item.strip()] if action else None
    rows, total = audit_service.project_audit_trail(
        db, project, actions=actions, page=page, page_size=page_size
    )
    return AuditTrailResponse(
        items=[AuditLogRead.model_validate(row) for row in rows],
        meta=build_page_meta(total, page, page_size),
    )


__all__ = ["router"]
