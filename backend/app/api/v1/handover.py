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
import textwrap
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.ai.provider import LLMProvider
from app.api.v1.memory import get_llm_provider, require_provider
from app.core.dependencies import CurrentUser, DbSession, resolve_project_access
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.models.enums import WorkspaceRole
from app.models.handover import Handover, HandoverVersion, SuccessorHandoverPackage, SuccessorHandoverVerification
from app.models.repository_intelligence import RepositoryConnection, RepositorySnapshot
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
from app.services.handover_intelligence import apply_human_edits, build_successor_handover, persist_successor_package

router = APIRouter(prefix="/projects", tags=["handover"])


class SuccessorPackageEdit(BaseModel):
    sections: list[dict] = Field(max_length=20)
    tasks: list[dict] = Field(max_length=500)
    reviewer_notes: str = Field(default="", max_length=4000)


class SuccessorVerificationInput(BaseModel):
    activity_type: Literal["environment_setup", "architecture_understanding", "dependency_understanding", "historical_context", "independent_task"]
    status: Literal["in_progress", "verified", "needs_review", "blocked"]
    result: str = Field(min_length=1, max_length=4000)
    evidence: list[dict] = Field(default_factory=list, max_length=100)
    user_confirmed: bool = False


def _package(db, project_id: uuid.UUID, package_id: uuid.UUID) -> SuccessorHandoverPackage:
    row = db.get(SuccessorHandoverPackage, package_id)
    if row is None or row.project_id != project_id:
        raise NotFoundError("Successor handover package not found.")
    return row


def _package_payload(row: SuccessorHandoverPackage) -> dict:
    return {
        "id": str(row.id), "project_id": str(row.project_id),
        "repository_id": str(row.repository_id), "snapshot_id": str(row.snapshot_id),
        "previous_package_id": str(row.previous_package_id) if row.previous_package_id else None,
        "role": row.successor_role, "version": row.version_number, "status": row.status,
        "content": row.content, "source_run_ids": row.source_run_ids,
        "created_by_id": str(row.created_by_id) if row.created_by_id else None,
        "reviewed_by_id": str(row.reviewed_by_id) if row.reviewed_by_id else None,
        "approved_at": row.approved_at, "created_at": row.created_at,
    }


@router.get(
    "/{project_id}/handover-intelligence",
    summary="Assemble a role-aware successor handover from persisted repository analyses",
)
def get_handover_intelligence(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    role: str = Query(default="project_maintainer", max_length=40),
) -> dict:
    """Return a fresh snapshot-bound handover package without claiming approval.

    This is a read-only deterministic assembly. Editing, approval and immutable
    publication continue through the established HandoverVersion workflow.
    """
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    return build_successor_handover(db, project_id, role)


@router.get(
    "/{project_id}/handover-intelligence/export.md",
    summary="Export the current snapshot-bound successor package as Markdown",
    response_class=Response,
)
def export_handover_intelligence(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    role: str = Query(default="project_maintainer", max_length=40),
) -> Response:
    resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    package = build_successor_handover(db, project_id, role)
    lines = [
        "# Successor handover", "",
        f"Role: {package['role']}",
        f"Snapshot: `{package['snapshot_commit'] or package['snapshot_branch']}` ({package['snapshot_id']})",
        f"Generated: {package['generated_at']}", "",
        "> Generated from persisted repository analyses. Inferred content is not verified fact; this export is not an approved handover.", "",
    ]
    for section in package["sections"]:
        lines.extend([f"## {section['title']}", ""])
        for item in section["items"]:
            text = item.get("text") or item.get("content") or item.get("title") or ""
            lines.append(f"- {text}")
            for evidence in item.get("evidence", []):
                label = evidence.get("label") or evidence.get("file_path") or evidence.get("source_name") or "Evidence"
                target = evidence.get("url")
                lines.append(f"  - Evidence: [{label}]({target})" if target else f"  - Evidence: {label}")
        if not section["items"]:
            lines.append("- Not established in available snapshot evidence.")
        lines.append("")
    lines.extend(["## Readiness", "", f"Status: **{package['readiness']['status']}**", ""])
    for dimension in package["readiness"]["dimensions"]:
        lines.append(f"- **{dimension['dimension']}** — {dimension['status']}: {dimension['explanation']}")
    lines.extend(["", "## Onboarding path", ""])
    for step in package["onboarding"]:
        lines.append(f"- **{step['title']}** — {step['objective']}")
    lines.extend(["", "## Limitations", "", *[f"- {item}" for item in package["limitations"]], ""])
    return Response(
        content="\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="successor-handover-{project_id}.md"'},
    )


@router.post(
    "/{project_id}/handover-intelligence",
    status_code=status.HTTP_201_CREATED,
    summary="Generate and preserve a new snapshot-bound successor handover draft",
)
def create_successor_handover(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    role: str = Query(default="project_maintainer", max_length=40),
) -> dict:
    project, _role = resolve_project_access(db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER)
    content = build_successor_handover(db, project_id, role)
    row = persist_successor_package(db, content, user_id=user.id)
    audit_service.record(db, action="successor_handover_generated", user_id=user.id, workspace_id=project.workspace_id, resource_type="successor_handover_package", resource_id=row.id, metadata={"project_id": str(project_id), "role": role, "version": row.version_number, "snapshot_id": str(row.snapshot_id)})
    return _package_payload(row)


@router.get(
    "/{project_id}/handover-intelligence/versions",
    summary="List generated and reviewed successor handover revisions",
)
def list_successor_handover_versions(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    role: str = Query(default="project_maintainer", max_length=80),
) -> list[dict]:
    resolve_project_access(db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER)
    rows = db.scalars(select(SuccessorHandoverPackage).where(
        SuccessorHandoverPackage.project_id == project_id,
        SuccessorHandoverPackage.successor_role == role,
    ).order_by(SuccessorHandoverPackage.version_number.desc()).limit(100)).all()
    output = [_package_payload(row) for row in rows]
    current_snapshot = db.scalar(select(RepositorySnapshot.id).join(
        RepositoryConnection, RepositorySnapshot.repository_connection_id == RepositoryConnection.id
    ).where(RepositoryConnection.project_id == project_id).order_by(
        RepositoryConnection.created_at.desc(), RepositorySnapshot.created_at.desc()
    ).limit(1)) if rows else None
    for item in output:
        item["stale"] = bool(current_snapshot and item["snapshot_id"] != str(current_snapshot))
    return output


@router.patch(
    "/{project_id}/handover-intelligence/versions/{package_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Save reviewed sections and tasks as a new immutable package revision",
)
def edit_successor_handover(
    project_id: uuid.UUID,
    package_id: uuid.UUID,
    payload: SuccessorPackageEdit,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    project, _role = _reviewer(db, project_id=project_id, user=user)
    row = _package(db, project_id, package_id)
    if row.status == "superseded":
        raise ConflictError("A superseded package cannot be edited; create a new generation.")
    content = apply_human_edits(dict(row.content or {}), payload.sections, payload.tasks)
    if payload.reviewer_notes.strip():
        notes = list(content.get("reviewer_notes", []))
        notes.append({"text": payload.reviewer_notes.strip(), "reviewer_id": str(user.id), "at": datetime.now(timezone.utc).isoformat()})
        content["reviewer_notes"] = notes
    revised = persist_successor_package(db, content, user_id=user.id, previous=row)
    audit_service.record(db, action="successor_handover_edited", user_id=user.id, workspace_id=project.workspace_id, resource_type="successor_handover_package", resource_id=revised.id, metadata={"project_id": str(project_id), "previous_package_id": str(row.id), "version": revised.version_number})
    return _package_payload(revised)


@router.post(
    "/{project_id}/handover-intelligence/versions/{package_id}/submit",
    summary="Submit a successor package revision for human approval",
)
def submit_successor_handover(
    project_id: uuid.UUID, package_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> dict:
    project, _role = _reviewer(db, project_id=project_id, user=user)
    row = _package(db, project_id, package_id)
    if row.status != "draft":
        raise ConflictError("Only a draft successor package can be submitted for review.")
    row.status = "in_review"
    db.commit()
    db.refresh(row)
    audit_service.record(db, action="successor_handover_submitted", user_id=user.id, workspace_id=project.workspace_id, resource_type="successor_handover_package", resource_id=row.id, metadata={"project_id": str(project_id), "version": row.version_number})
    return _package_payload(row)


@router.post(
    "/{project_id}/handover-intelligence/versions/{package_id}/approve",
    summary="Approve a reviewed successor handover revision",
)
def approve_successor_handover(
    project_id: uuid.UUID, package_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> dict:
    _project, role = _reviewer(db, project_id=project_id, user=user)
    if role not in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}:
        raise ValidationAppError("Only a workspace owner or admin may approve handover packages.")
    row = _package(db, project_id, package_id)
    if row.status != "in_review":
        raise ConflictError("Submit the draft for review before approving it.")
    row.status = "approved"
    row.reviewed_by_id = user.id
    row.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    audit_service.record(db, action="successor_handover_approved", user_id=user.id, workspace_id=_project.workspace_id, resource_type="successor_handover_package", resource_id=row.id, metadata={"project_id": str(project_id), "version": row.version_number})
    return _package_payload(row)


@router.get(
    "/{project_id}/handover-intelligence/versions/{package_id}/verification",
    summary="List observable successor verification activities",
)
def list_successor_verification(
    project_id: uuid.UUID, package_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[dict]:
    resolve_project_access(db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER)
    _package(db, project_id, package_id)
    rows = db.scalars(select(SuccessorHandoverVerification).where(
        SuccessorHandoverVerification.package_id == package_id
    ).order_by(SuccessorHandoverVerification.created_at.desc()).limit(100)).all()
    return [{"id": str(row.id), "activity_type": row.activity_type, "status": row.status, "evidence": row.evidence, "result": row.result, "verified_by_id": str(row.verified_by_id) if row.verified_by_id else None, "verified_at": row.verified_at, "created_at": row.created_at} for row in rows]


@router.post(
    "/{project_id}/handover-intelligence/versions/{package_id}/verification",
    status_code=status.HTTP_201_CREATED,
    summary="Record a user-confirmed successor verification activity",
)
def record_successor_verification(
    project_id: uuid.UUID, package_id: uuid.UUID, payload: SuccessorVerificationInput,
    user: CurrentUser, db: DbSession,
) -> dict:
    project, _role = resolve_project_access(db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER)
    package = _package(db, project_id, package_id)
    if payload.status == "verified" and not payload.user_confirmed:
        raise ValidationAppError("A verification cannot be marked verified without explicit user confirmation.")
    row = SuccessorHandoverVerification(
        package_id=package.id, activity_type=payload.activity_type, status=payload.status,
        result=payload.result.strip(), evidence=payload.evidence,
        verified_by_id=user.id if payload.status == "verified" else None,
        verified_at=datetime.now(timezone.utc) if payload.status == "verified" else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    audit_service.record(db, action="successor_verification_recorded", user_id=user.id, workspace_id=project.workspace_id, resource_type="successor_handover_verification", resource_id=row.id, metadata={"project_id": str(project_id), "package_id": str(package.id), "activity_type": row.activity_type, "status": row.status})
    return {"id": str(row.id), "activity_type": row.activity_type, "status": row.status, "result": row.result, "evidence": row.evidence, "verified_at": row.verified_at}


@router.get(
    "/{project_id}/handover-intelligence/versions/{package_id}/export.pdf",
    summary="Export a saved successor handover revision as PDF",
    response_class=Response,
)
def export_successor_pdf(
    project_id: uuid.UUID, package_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Response:
    project, _role = resolve_project_access(db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER)
    package = _package(db, project_id, package_id)
    import pymupdf

    content = package.content or {}
    document = pymupdf.open()
    page = document.new_page()
    width, height = page.rect.width, page.rect.height
    margin, y = 54, 60

    def add_line(value: str, size: float = 10, bold: bool = False) -> None:
        nonlocal page, y
        for wrapped in textwrap.wrap(value, width=max(24, int((width - 2 * margin) / (size * .53))), break_long_words=True) or [""]:
            if y > height - 55:
                page = document.new_page()
                y = 60
            page.insert_text((margin, y), wrapped, fontsize=size, fontname="hebo" if bold else "helv")
            y += size * 1.45

    add_line("Successor handover", 18, True)
    add_line(f"Role: {package.successor_role} · Version {package.version_number} · Status: {package.status}", 10)
    add_line(f"Snapshot: {(content.get('snapshot_commit') or content.get('snapshot_branch') or package.snapshot_id)}", 9)
    add_line("Generated content may include inferences and is not verified fact unless explicitly reviewed.", 9)
    for section in content.get("sections", []):
        add_line(str(section.get("title", "Section")), 13, True)
        for item in section.get("items", []):
            add_line("• " + str(item.get("text") or item.get("content") or item.get("title") or ""), 10)
            for evidence in item.get("evidence", []):
                add_line("  Evidence: " + str(evidence.get("file_path") or evidence.get("label") or evidence.get("source_name") or "reference"), 8)
    for page_number, pdf_page in enumerate(document, start=1):
        pdf_page.insert_text((width - 68, height - 24), f"Page {page_number}", fontsize=8, fontname="helv")
    payload_bytes = document.tobytes()
    document.close()
    audit_service.record(db, action="handover_exported", user_id=user.id, workspace_id=project.workspace_id, resource_type="successor_handover_package", resource_id=package.id, metadata={"project_id": str(project_id), "format": "pdf", "version": package.version_number})
    return Response(content=payload_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="successor-handover-{package.id}-v{package.version_number}.pdf"'})

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
