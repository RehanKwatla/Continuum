"""Public GitHub repository validation, asynchronous analysis and exploration."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.dependencies import CurrentUser, DbSession, resolve_project_access
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError, UpstreamError
from app.models.enums import ACTIVE_REPOSITORY_INGESTION_STATUSES, RepositoryIngestionStatus, WorkspaceRole
from app.models.enums import CodeAnalysisStatus
from app.models.code_intelligence import ArchitectureComponent, CodeAnalysisRun, CodeSymbol, EntryPoint, ExternalDependency, LanguageStatistic, ModuleDependency, TechnologyDetection
from app.models.git_history import CommitFileChange, CommitInsight, HistoryAnalysisRun
from app.models.repository_intelligence import (
    CommitRecord, IssueRecord, PullRequestRecord, RepositoryConnection, RepositorySnapshot,
    RepositoryFile,
)
from app.models.workspace import Workspace
from app.schemas.repository_intelligence import (
    AnalysisStartedResponse, RepositoryAnalyseRequest, RepositoryValidateRequest,
)
from app.services.public_github import GitHubApiError, RepositoryUrlError
from app.services.repository_intelligence import (
    connection_payload, paged_records, run_snapshot, snapshot_payload, validate_repository_url,
)
from app.services.code_analysis.parser import PARSER_VERSION
from app.services.code_analysis.service import run_code_analysis, run_payload
from app.services.git_history_intelligence import ANALYSIS_VERSION as HISTORY_ANALYSIS_VERSION, analyze_history, history_payload

router = APIRouter(prefix="/repositories", tags=["repository-intelligence"])


def _code_run(db, repository_id, user, run_id=None):
    _connection(db, repository_id, user)
    if run_id:
        run = db.get(CodeAnalysisRun, run_id)
        if not run:
            raise NotFoundError("Code analysis run not found.")
        snapshot = db.get(RepositorySnapshot, run.snapshot_id)
        if not snapshot or snapshot.repository_connection_id != repository_id:
            raise NotFoundError("Code analysis run not found.")
        return run
    return db.scalar(select(CodeAnalysisRun).join(RepositorySnapshot).where(RepositorySnapshot.repository_connection_id == repository_id).order_by(CodeAnalysisRun.created_at.desc()).limit(1))


@router.post("/{repository_id}/code-analysis", status_code=status.HTTP_202_ACCEPTED)
def start_code_analysis(repository_id: uuid.UUID, background_tasks: BackgroundTasks, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None):
    _connection(db, repository_id, user)
    snapshot = db.get(RepositorySnapshot, snapshot_id) if snapshot_id else db.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_connection_id == repository_id).order_by(RepositorySnapshot.created_at.desc()).limit(1))
    if not snapshot or snapshot.repository_connection_id != repository_id:
        raise NotFoundError("Repository snapshot not found.")
    if snapshot.ingestion_status not in {RepositoryIngestionStatus.COMPLETED, RepositoryIngestionStatus.PARTIALLY_COMPLETED}:
        raise ConflictError("Code analysis requires a completed repository snapshot.")
    run = db.scalar(select(CodeAnalysisRun).where(CodeAnalysisRun.snapshot_id == snapshot.id, CodeAnalysisRun.parser_version == PARSER_VERSION))
    if run is None:
        run = CodeAnalysisRun(snapshot_id=snapshot.id, parser_version=PARSER_VERSION, status=CodeAnalysisStatus.PENDING)
        db.add(run)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            run = db.scalar(select(CodeAnalysisRun).where(CodeAnalysisRun.snapshot_id == snapshot.id, CodeAnalysisRun.parser_version == PARSER_VERSION))
    if run.status in {CodeAnalysisStatus.PENDING, CodeAnalysisStatus.FAILED}:
        run.status = CodeAnalysisStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        run.completed_at = None
        db.commit()
        background_tasks.add_task(run_code_analysis, run.id)
    return run_payload(run)


@router.get("/{repository_id}/code-analysis/{analysis_id}")
def get_code_analysis(repository_id: uuid.UUID, analysis_id: uuid.UUID, user: CurrentUser, db: DbSession):
    run = _code_run(db, repository_id, user, analysis_id)
    return run_payload(run)


def _analysis_records(repository_id, user, db, model, run_id=None, page=1, page_size=50):
    run = _code_run(db, repository_id, user, run_id)
    if not run:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}
    query = select(model).where(model.analysis_run_id == run.id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(model.created_at).offset((page - 1) * page_size).limit(page_size)).all()
    items = [{column.key: getattr(row, column.key) for column in model.__table__.columns if column.key != "created_at"} for row in rows]
    return {"items": items, "page": page, "page_size": page_size, "total": total, "analysis_id": run.id}


@router.get("/{repository_id}/languages")
def code_languages(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, analysis_id: uuid.UUID | None = None):
    run = _code_run(db, repository_id, user, analysis_id)
    return {"items": [] if not run else db.scalars(select(LanguageStatistic).where(LanguageStatistic.analysis_run_id == run.id)).all(), "analysis_id": run.id if run else None, "summary": run.languages_summary if run else {}}


@router.get("/{repository_id}/technologies")
def code_technologies(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, analysis_id: uuid.UUID | None = None):
    return _analysis_records(repository_id, user, db, TechnologyDetection, analysis_id)


@router.get("/{repository_id}/structure")
def code_structure(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, analysis_id: uuid.UUID | None = None):
    run = _code_run(db, repository_id, user, analysis_id)
    return run.architecture_summary if run else {"tree": [], "files": 0, "directories": 0, "analysed_files": 0, "skipped_files": 0, "category_counts": {}}


@router.get("/{repository_id}/entry-points")
def code_entry_points(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, analysis_id: uuid.UUID | None = None):
    return _analysis_records(repository_id, user, db, EntryPoint, analysis_id)


@router.get("/{repository_id}/symbols")
def code_symbols(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, analysis_id: uuid.UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    return _analysis_records(repository_id, user, db, CodeSymbol, analysis_id, page, page_size)


@router.get("/{repository_id}/dependencies/internal")
def code_internal_dependencies(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, analysis_id: uuid.UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    return _analysis_records(repository_id, user, db, ModuleDependency, analysis_id, page, page_size)


@router.get("/{repository_id}/dependencies/external")
def code_external_dependencies(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, analysis_id: uuid.UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=100)):
    return _analysis_records(repository_id, user, db, ExternalDependency, analysis_id, page, page_size)


@router.get("/{repository_id}/architecture")
def code_architecture(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, analysis_id: uuid.UUID | None = None):
    run = _code_run(db, repository_id, user, analysis_id)
    if not run:
        return {"items": [], "nodes": [], "edges": [], "analysis_id": None}
    components = db.scalars(select(ArchitectureComponent).where(ArchitectureComponent.analysis_run_id == run.id)).all()
    edges = db.scalars(select(ModuleDependency).where(ModuleDependency.analysis_run_id == run.id)).all()
    graph_nodes = {name for edge in edges for name in (edge.source_file, edge.target_file or edge.target_module)}
    return {"items": [{"component_name": c.component_name, "category": c.category, "confidence": c.confidence, "evidence": c.evidence, "file_paths": c.file_paths, "connected_components": c.connected_components} for c in components], "nodes": [{"id": name, "label": name, "category": "module"} for name in sorted(graph_nodes)], "edges": [{"source": e.source_file, "target": e.target_file or e.target_module, "relationship": e.relationship_type, "resolution_status": e.resolution_status, "evidence": [e.source_file, e.line_number]} for e in edges], "analysis_id": run.id}


@router.get("/{repository_id}/analysis-summary")
def code_analysis_summary(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, analysis_id: uuid.UUID | None = None):
    run = _code_run(db, repository_id, user, analysis_id)
    return run_payload(run) if run else {"status": "not_started", "message": "Start code analysis after a repository snapshot completes."}


@router.post("/{repository_id}/history-analysis")
def start_history_analysis(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None):
    connection = _connection(db, repository_id, user)
    snapshot = db.get(RepositorySnapshot, snapshot_id) if snapshot_id else db.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_connection_id == repository_id).order_by(RepositorySnapshot.created_at.desc()).limit(1))
    if not snapshot or snapshot.repository_connection_id != repository_id:
        raise NotFoundError("Repository snapshot not found.")
    if snapshot.ingestion_status not in {RepositoryIngestionStatus.COMPLETED, RepositoryIngestionStatus.PARTIALLY_COMPLETED}:
        raise ConflictError("History analysis requires a completed repository snapshot.")
    return history_payload(analyze_history(db, snapshot, connection))


@router.get("/{repository_id}/history-analysis")
def get_history_analysis(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None):
    _connection(db, repository_id, user)
    snapshot = db.get(RepositorySnapshot, snapshot_id) if snapshot_id else db.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_connection_id == repository_id).order_by(RepositorySnapshot.created_at.desc()).limit(1))
    if not snapshot or snapshot.repository_connection_id != repository_id:
        raise NotFoundError("Repository snapshot not found.")
    run = db.scalar(select(HistoryAnalysisRun).where(HistoryAnalysisRun.snapshot_id == snapshot.id, HistoryAnalysisRun.analysis_version == HISTORY_ANALYSIS_VERSION))
    return history_payload(run) if run else {"status": "not_started", "snapshot_id": snapshot.id}


@router.get("/{repository_id}/commit-changes")
def repository_commit_changes(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    _connection(db, repository_id, user)
    snapshot = db.get(RepositorySnapshot, snapshot_id) if snapshot_id else db.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_connection_id == repository_id).order_by(RepositorySnapshot.created_at.desc()).limit(1))
    if not snapshot or snapshot.repository_connection_id != repository_id:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}
    query = select(CommitFileChange).where(CommitFileChange.snapshot_id == snapshot.id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(CommitFileChange.commit_sha, CommitFileChange.file_path).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"commit_sha": row.commit_sha, "file_path": row.file_path, "status": row.status, "previous_filename": row.previous_filename, "additions": row.additions, "deletions": row.deletions, "changes": row.changes, "statistics_available": row.statistics_available, "patch_available": row.patch_available} for row in rows], "page": page, "page_size": page_size, "total": total, "snapshot_id": snapshot.id}


@router.get("/{repository_id}/commit-insights")
def repository_commit_insights(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    _connection(db, repository_id, user)
    snapshot = db.get(RepositorySnapshot, snapshot_id) if snapshot_id else db.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_connection_id == repository_id).order_by(RepositorySnapshot.created_at.desc()).limit(1))
    if not snapshot or snapshot.repository_connection_id != repository_id:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}
    query = select(CommitInsight).where(CommitInsight.snapshot_id == snapshot.id, CommitInsight.analysis_version == HISTORY_ANALYSIS_VERSION)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(CommitInsight.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"commit_sha": row.commit_sha, "category": row.category, "confidence": row.confidence, "classification_method": row.classification_method, "signals": row.signals, "summary": row.summary, "affected_components": row.affected_components, "source_references": row.source_references} for row in rows], "page": page, "page_size": page_size, "total": total, "snapshot_id": snapshot.id}


def _error(exc: Exception):
    if isinstance(exc, RepositoryUrlError):
        raise ValidationAppError(str(exc)) from exc
    if isinstance(exc, GitHubApiError):
        if exc.status == 404:
            raise NotFoundError(str(exc)) from exc
        if exc.status == 429:
            raise UpstreamError(str(exc), code="github_rate_limited") from exc
        raise UpstreamError(str(exc), code="github_api_error", details={"status_code": exc.status}) from exc
    raise exc


@router.post("/validate", summary="Validate and inspect a public GitHub repository")
def validate_repository(payload: RepositoryValidateRequest):
    try:
        parsed, metadata, branches, selected = validate_repository_url(payload.repository_url)
        return {"valid": True, "repository": metadata, "branches": branches, "selected_branch": selected}
    except (RepositoryUrlError, GitHubApiError) as exc:
        _error(exc)


@router.post("/projects/{project_id}/analyse", response_model=AnalysisStartedResponse, status_code=status.HTTP_202_ACCEPTED)
def analyse_repository(
    project_id: uuid.UUID,
    payload: RepositoryAnalyseRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    user: CurrentUser,
    db: DbSession,
):
    project, _ = resolve_project_access(db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER)
    if not request.headers.get("authorization"):
        settings = get_settings()
        workspace = db.get(Workspace, project.workspace_id)
        if not settings.public_demo_mode or not workspace or workspace.name != settings.public_demo_workspace_name:
            raise ForbiddenError("Public repository analysis is available only in the designated demo workspace.")
    try:
        parsed, metadata, branches, selected = validate_repository_url(payload.repository_url)
    except (RepositoryUrlError, GitHubApiError) as exc:
        _error(exc)
    branch = payload.branch or selected
    branch_data = next((item for item in branches if item["name"] == branch), None)
    if branch_data is None:
        raise ValidationAppError("Select a branch returned by GitHub.")

    connection = db.scalar(select(RepositoryConnection).where(
        RepositoryConnection.project_id == project.id,
        RepositoryConnection.provider == "github",
        RepositoryConnection.owner == metadata["owner"],
        RepositoryConnection.repository_name == metadata["name"],
    ))
    if connection is None:
        connection = RepositoryConnection(
            project_id=project.id, owner=metadata["owner"], repository_name=metadata["name"],
            repository_url=metadata["canonical_url"], default_branch=metadata["default_branch"],
            selected_branch=branch, external_id=None, description=metadata["description"],
            language=metadata["language"], languages=metadata["languages"], stars=metadata["stars"],
            forks=metadata["forks"], open_issues=metadata["open_issues"], license_name=metadata["license"],
            repository_created_at=metadata["created_at"], repository_updated_at=metadata["updated_at"],
            repository_pushed_at=metadata["pushed_at"], branches=branches,
        )
        db.add(connection)
        db.flush()
    else:
        connection.repository_url = metadata["canonical_url"]
        connection.default_branch, connection.selected_branch = metadata["default_branch"], branch
        connection.branches, connection.languages = branches, metadata["languages"]

    active = db.scalar(select(RepositorySnapshot).where(
        RepositorySnapshot.repository_connection_id == connection.id,
        RepositorySnapshot.branch == branch,
        RepositorySnapshot.ingestion_status.in_(ACTIVE_REPOSITORY_INGESTION_STATUSES),
    ).order_by(RepositorySnapshot.created_at.desc()).limit(1))
    if active:
        db.commit()
        return AnalysisStartedResponse(repository_id=connection.id, analysis_run_id=active.id, status=active.ingestion_status.value, stage=active.ingestion_status.value)
    settings = get_settings()
    snapshot = RepositorySnapshot(repository_connection_id=connection.id, requested_by_id=user.id, branch=branch, ingestion_status=RepositoryIngestionStatus.QUEUED, limits={"files": settings.repository_max_files, "file_bytes": settings.repository_max_file_bytes, "total_content_bytes": settings.repository_max_content_bytes, "tree_entries": settings.repository_max_tree_entries, "commits": settings.repository_max_commits, "issues": settings.repository_max_issues, "pull_requests": settings.repository_max_pull_requests, "api_requests": settings.repository_max_api_requests, "duration_seconds": settings.repository_max_duration_seconds, "tree_depth": settings.repository_max_tree_depth})
    db.add(snapshot)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        connection = db.scalar(select(RepositoryConnection).where(
            RepositoryConnection.project_id == project.id,
            RepositoryConnection.provider == "github",
            RepositoryConnection.owner == metadata["owner"],
            RepositoryConnection.repository_name == metadata["name"],
        ))
        active = db.scalar(select(RepositorySnapshot).where(
            RepositorySnapshot.repository_connection_id == connection.id,
            RepositorySnapshot.branch == branch,
            RepositorySnapshot.ingestion_status.in_(ACTIVE_REPOSITORY_INGESTION_STATUSES),
        ).order_by(RepositorySnapshot.created_at.desc()).limit(1)) if connection else None
        if active:
            return AnalysisStartedResponse(repository_id=connection.id, analysis_run_id=active.id, status=active.ingestion_status.value, stage=active.ingestion_status.value)
        raise ConflictError("Repository analysis could not be queued because another run changed its state.") from exc
    db.refresh(snapshot)
    background_tasks.add_task(run_snapshot, snapshot.id)
    return AnalysisStartedResponse(repository_id=connection.id, analysis_run_id=snapshot.id, status="queued", stage="queued")


@router.get("/projects/{project_id}")
def project_repositories(project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    resolve_project_access(db, project_id=project_id, user=user, required_role=WorkspaceRole.VIEWER)
    connections = db.scalars(select(RepositoryConnection).where(RepositoryConnection.project_id == project_id).order_by(RepositoryConnection.updated_at.desc())).all()
    return {"items": [connection_payload(db, row) for row in connections]}


def _connection(db, repository_id: uuid.UUID, user):
    row = db.get(RepositoryConnection, repository_id)
    if not row:
        raise NotFoundError("Repository not found.")
    resolve_project_access(db, project_id=row.project_id, user=user, required_role=WorkspaceRole.VIEWER)
    return row


@router.get("/{repository_id}")
def repository_detail(repository_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return connection_payload(db, _connection(db, repository_id, user))


@router.get("/{repository_id}/branches")
def repository_branches(repository_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return {"items": _connection(db, repository_id, user).branches or []}


@router.get("/{repository_id}/analysis/{run_id}")
def repository_analysis(repository_id: uuid.UUID, run_id: uuid.UUID, user: CurrentUser, db: DbSession):
    _connection(db, repository_id, user)
    row = db.get(RepositorySnapshot, run_id)
    if not row or row.repository_connection_id != repository_id:
        raise NotFoundError("Repository analysis run not found.")
    return snapshot_payload(row)


@router.get("/{repository_id}/snapshot")
def latest_snapshot(repository_id: uuid.UUID, user: CurrentUser, db: DbSession):
    _connection(db, repository_id, user)
    row = db.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_connection_id == repository_id).order_by(RepositorySnapshot.created_at.desc()).limit(1))
    if not row:
        raise NotFoundError("No repository snapshot is available.")
    return snapshot_payload(row)


@router.get("/{repository_id}/files")
def repository_files(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), snapshot_id: uuid.UUID | None = None):
    _connection(db, repository_id, user)
    snap = db.get(RepositorySnapshot, snapshot_id) if snapshot_id else db.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_connection_id == repository_id).order_by(RepositorySnapshot.created_at.desc()).limit(1))
    if not snap or snap.repository_connection_id != repository_id:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}
    query = select(RepositoryFile).where(RepositoryFile.snapshot_id == snap.id)
    total = db.query(RepositoryFile).filter(RepositoryFile.snapshot_id == snap.id).count()
    rows = db.scalars(query.order_by(RepositoryFile.path).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"id": r.id, "path": r.path, "file_name": r.file_name, "directory_path": r.directory_path, "extension": r.extension, "size": r.size, "blob_sha": r.blob_sha, "analysis_status": r.analysis_status.value, "skip_reason": r.skip_reason, "source_id": r.source_id} for r in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/{repository_id}/commits")
def repository_commits(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    _connection(db, repository_id, user)
    return paged_records(db, CommitRecord, repository_id, page, page_size)


@router.get("/{repository_id}/issues")
def repository_issues(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    _connection(db, repository_id, user)
    return paged_records(db, IssueRecord, repository_id, page, page_size)


@router.get("/{repository_id}/pull-requests")
def repository_pull_requests(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    _connection(db, repository_id, user)
    return paged_records(db, PullRequestRecord, repository_id, page, page_size)
