"""Source endpoints: upload, list, detail and delete.

Everything a client can learn here is read back from PostgreSQL — no synthetic
source records are ever returned.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile, status

from app.core.config import settings
from app.core.dependencies import (
    CurrentUser,
    DbSession,
    resolve_project_access,
)
from app.core.errors import NotFoundError, ValidationAppError
from app.models.enums import ProcessingStatus, SourceType, WorkspaceRole
from app.models.source import Source
from app.repositories.sources import SourcesRepository
from app.schemas.common import build_page_meta
from app.schemas.source import (
    SourceDeleteResponse,
    SourceListResponse,
    SourceRead,
    SourceSummary,
    UploadResponse,
)
from app.services.ingestion_service import IngestionService

logger = logging.getLogger("continuum.api.sources")

router = APIRouter(tags=["sources"])

_PREVIEW_CHARS = 400


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------
def to_source_summary(source: Source) -> SourceSummary:
    summary = SourceSummary.model_validate(source)
    raw = (source.content or "").strip()
    if raw:
        collapsed = " ".join(raw.split())
        summary.content_preview = (
            collapsed[:_PREVIEW_CHARS] + "…" if len(collapsed) > _PREVIEW_CHARS else collapsed
        )
    return summary


def to_source_read(source: Source) -> SourceRead:
    # Validate straight from the ORM object: the ``metadata`` field uses the
    # ``meta`` validation alias, so a ``SourceSummary`` -> ``model_dump`` ->
    # ``SourceRead`` round-trip would silently drop it.
    read = SourceRead.model_validate(source)
    raw = (source.content or "").strip()
    if raw:
        collapsed = " ".join(raw.split())
        read.content_preview = (
            collapsed[:_PREVIEW_CHARS] + "…" if len(collapsed) > _PREVIEW_CHARS else collapsed
        )
    return read


def _load_source(db, source_id: uuid.UUID) -> Source:
    source = SourcesRepository(db).get(source_id)
    if source is None:
        raise NotFoundError("Source not found.")
    return source


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post(
    "/projects/{project_id}/sources/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload PDF / Markdown / TXT / ZIP sources into a project",
)
def upload_sources(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    files: list[UploadFile] = File(..., description="One or more supported files."),
) -> UploadResponse:
    if not files:
        raise ValidationAppError("At least one file is required.")

    project, _ = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )

    max_bytes = settings.max_upload_size_bytes
    for upload in files:
        if upload.size is not None and upload.size > max_bytes:
            raise ValidationAppError(
                f"'{upload.filename}' exceeds the {max_bytes} byte upload limit.",
                details={"max_upload_size_bytes": max_bytes},
            )

    return IngestionService(db).ingest_uploads(project, files)


@router.get(
    "/projects/{project_id}/sources",
    response_model=SourceListResponse,
    summary="List ingested sources for a project",
)
def list_sources(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    source_type: SourceType | None = Query(default=None),
    processing_status: ProcessingStatus | None = Query(default=None),
    search: str | None = Query(default=None, max_length=300),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> SourceListResponse:
    project, _ = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    repo = SourcesRepository(db)
    offset = (page - 1) * page_size
    rows, total = repo.list_for_project(
        project.id,
        source_type=source_type,
        processing_status=processing_status,
        search=search,
        limit=page_size,
        offset=offset,
    )
    return SourceListResponse(
        items=[to_source_summary(row) for row in rows],
        meta=build_page_meta(total, page, page_size),
        type_counts=repo.counts_by_type(project.id),
        status_counts=repo.counts_by_status(project.id),
    )


@router.get("/sources/{source_id}", response_model=SourceRead, summary="Get one source")
def get_source(source_id: uuid.UUID, user: CurrentUser, db: DbSession) -> SourceRead:
    source = _load_source(db, source_id)
    resolve_project_access(
        db, project_id=source.project_id, user=user, required_role=WorkspaceRole.VIEWER
    )
    return to_source_read(source)


@router.delete(
    "/sources/{source_id}",
    response_model=SourceDeleteResponse,
    summary="Delete a source",
)
def delete_source(
    source_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> SourceDeleteResponse:
    source = _load_source(db, source_id)
    resolve_project_access(
        db, project_id=source.project_id, user=user, required_role=WorkspaceRole.MEMBER
    )

    storage_key = source.storage_key
    project_id = source.project_id
    db.delete(source)
    db.commit()

    if storage_key:
        _remove_stored_file(project_id, storage_key)

    from app.services import audit_service

    audit_service.record(
        db,
        action="source.deleted",
        user_id=user.id,
        resource_type="source",
        resource_id=source_id,
        metadata={"storage_key_present": bool(storage_key)},
    )
    return SourceDeleteResponse(id=source_id, deleted=True)


def _remove_stored_file(project_id: uuid.UUID, storage_key: str) -> None:
    """Best-effort removal of an archived upload; never fails the request."""
    try:
        root = Path(settings.upload_dir).resolve()
        target = (root / str(project_id) / storage_key).resolve()
        if not str(target).startswith(str(root)):
            logger.error("Refusing to delete a file outside the upload root.")
            return
        if target.is_file():
            target.unlink()
    except OSError:  # pragma: no cover - filesystem dependent
        logger.warning("Could not remove stored upload %s", storage_key)
