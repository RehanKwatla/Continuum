"""Public GitHub repository validation, asynchronous analysis and exploration."""
from __future__ import annotations

import uuid
import re
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
from app.models.repository_knowledge import (
    KnowledgeAnalysisRun, KnowledgeConflict, KnowledgeEntity, KnowledgeEvidence,
    KnowledgeGap, KnowledgeRelationship, KnowledgeUnit, ProjectAssumption,
)
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
from app.services.repository_knowledge import ANALYSIS_VERSION as KNOWLEDGE_ANALYSIS_VERSION, run_knowledge_analysis, run_payload as knowledge_run_payload

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


def _knowledge_run(db, repository_id, user, snapshot_id=None, run_id=None):
    _connection(db, repository_id, user)
    if run_id:
        run = db.get(KnowledgeAnalysisRun, run_id)
        snapshot = db.get(RepositorySnapshot, run.snapshot_id) if run else None
        if not run or not snapshot or snapshot.repository_connection_id != repository_id:
            raise NotFoundError("Knowledge analysis run not found.")
        return run
    query = select(KnowledgeAnalysisRun).join(RepositorySnapshot).where(RepositorySnapshot.repository_connection_id == repository_id)
    if snapshot_id:
        query = query.where(KnowledgeAnalysisRun.snapshot_id == snapshot_id)
    return db.scalar(query.order_by(KnowledgeAnalysisRun.created_at.desc()).limit(1))


@router.post("/{repository_id}/knowledge/analyse", status_code=status.HTTP_202_ACCEPTED)
def start_knowledge_analysis(repository_id: uuid.UUID, background_tasks: BackgroundTasks, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None):
    _connection(db, repository_id, user)
    snapshot = db.get(RepositorySnapshot, snapshot_id) if snapshot_id else db.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_connection_id == repository_id).order_by(RepositorySnapshot.created_at.desc()).limit(1))
    if not snapshot or snapshot.repository_connection_id != repository_id:
        raise NotFoundError("Repository snapshot not found.")
    if snapshot.ingestion_status not in {RepositoryIngestionStatus.COMPLETED, RepositoryIngestionStatus.PARTIALLY_COMPLETED}:
        raise ConflictError("Knowledge analysis requires a completed repository snapshot.")
    run = db.scalar(select(KnowledgeAnalysisRun).where(KnowledgeAnalysisRun.snapshot_id == snapshot.id, KnowledgeAnalysisRun.analysis_version == KNOWLEDGE_ANALYSIS_VERSION))
    if run is None:
        run = KnowledgeAnalysisRun(snapshot_id=snapshot.id, analysis_version=KNOWLEDGE_ANALYSIS_VERSION, status="queued", progress=0, coverage={})
        db.add(run)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            run = db.scalar(select(KnowledgeAnalysisRun).where(KnowledgeAnalysisRun.snapshot_id == snapshot.id, KnowledgeAnalysisRun.analysis_version == KNOWLEDGE_ANALYSIS_VERSION))
    if run.status in {"queued", "failed"}:
        run.status, run.progress, run.error_details = "queued", 0, None
        db.commit()
        background_tasks.add_task(run_knowledge_analysis, run.id)
    return knowledge_run_payload(run)


@router.get("/{repository_id}/knowledge/jobs/{job_id}")
def get_knowledge_job(repository_id: uuid.UUID, job_id: uuid.UUID, user: CurrentUser, db: DbSession):
    run = _knowledge_run(db, repository_id, user, run_id=job_id)
    return knowledge_run_payload(run)


@router.get("/{repository_id}/knowledge/overview")
def knowledge_overview(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None):
    _connection(db, repository_id, user)
    run = _knowledge_run(db, repository_id, user, snapshot_id=snapshot_id)
    if not run:
        return {"status": "not_started", "units": 0, "gaps": 0, "conflicts": 0, "assumptions": 0, "coverage": {}, "message": "Run knowledge analysis on a completed repository snapshot."}
    counts = {"units": db.scalar(select(func.count()).select_from(KnowledgeUnit).where(KnowledgeUnit.analysis_run_id == run.id)) or 0, "gaps": db.scalar(select(func.count()).select_from(KnowledgeGap).where(KnowledgeGap.analysis_run_id == run.id, KnowledgeGap.status.in_(["open", "under_review"]))) or 0, "conflicts": db.scalar(select(func.count()).select_from(KnowledgeConflict).where(KnowledgeConflict.analysis_run_id == run.id, KnowledgeConflict.status == "open")) or 0, "assumptions": db.scalar(select(func.count()).select_from(ProjectAssumption).where(ProjectAssumption.analysis_run_id == run.id, ProjectAssumption.verification_status == "unverified")) or 0}
    return {"status": run.status, "analysis": knowledge_run_payload(run), **counts, "coverage": run.coverage}


@router.get("/{repository_id}/knowledge/units")
def knowledge_units(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None, category: str | None = None, evidence_level: str | None = None, freshness: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    run = _knowledge_run(db, repository_id, user, snapshot_id=snapshot_id)
    if not run:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}
    query = select(KnowledgeUnit).where(KnowledgeUnit.analysis_run_id == run.id)
    if category:
        query = query.where(KnowledgeUnit.category == category)
    if evidence_level:
        query = query.where(KnowledgeUnit.evidence_level == evidence_level)
    if freshness:
        query = query.where(KnowledgeUnit.freshness_status == freshness)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(KnowledgeUnit.category, KnowledgeUnit.title).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for row in rows:
        evidence = db.scalars(select(KnowledgeEvidence).where(KnowledgeEvidence.knowledge_unit_id == row.id).order_by(KnowledgeEvidence.created_at)).all()
        items.append({"id": row.id, "category": row.category, "title": row.title, "content": row.content, "evidence_level": row.evidence_level, "confidence": row.confidence, "extraction_method": row.extraction_method, "freshness_status": row.freshness_status, "source_timestamp": row.source_timestamp, "evidence": [{"source_id": e.source_id, "source_type": e.source_type, "source_name": e.source_name, "file_path": e.file_path, "line_start": e.line_start, "line_end": e.line_end, "source_location": e.source_location, "source_url": e.source_url, "quote": e.quote, "source_timestamp": e.source_timestamp} for e in evidence]})
    return {"items": items, "page": page, "page_size": page_size, "total": total, "analysis_id": run.id}


@router.get("/{repository_id}/knowledge/graph")
def knowledge_graph(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=200)):
    run = _knowledge_run(db, repository_id, user, snapshot_id=snapshot_id)
    if not run:
        return {"nodes": [], "edges": [], "total": 0}
    query = select(KnowledgeEntity).where(KnowledgeEntity.analysis_run_id == run.id).order_by(KnowledgeEntity.entity_type, KnowledgeEntity.entity_name)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    nodes = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    ids = [node.id for node in nodes]
    edges = db.scalars(select(KnowledgeRelationship).where(KnowledgeRelationship.analysis_run_id == run.id, KnowledgeRelationship.source_entity_id.in_(ids), KnowledgeRelationship.target_entity_id.in_(ids)).limit(page_size * 3)).all() if ids else []
    return {"nodes": [{"id": n.id, "type": n.entity_type, "label": n.entity_name, "reference": n.canonical_reference, "metadata": n.metadata_json} for n in nodes], "edges": [{"source": e.source_entity_id, "target": e.target_entity_id, "type": e.relationship_type, "confidence": e.confidence, "evidence_level": e.evidence_level, "evidence_id": e.evidence_id} for e in edges], "page": page, "page_size": page_size, "total": total, "analysis_id": run.id}


@router.get("/{repository_id}/knowledge/decisions")
def knowledge_decisions(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    run = _knowledge_run(db, repository_id, user, snapshot_id=snapshot_id)
    if not run:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}
    query = select(KnowledgeUnit).where(KnowledgeUnit.analysis_run_id == run.id, KnowledgeUnit.category == "technical_decision_context")
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    return {"items": [{"id": u.id, "title": u.title, "summary": u.content, "status": "unclear", "evidence_level": u.evidence_level, "confidence": u.confidence} for u in db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()], "page": page, "page_size": page_size, "total": total, "note": "Stage 4 classifies commits but does not persist technical decision records; these are evidence excerpts, not accepted decisions."}


@router.get("/{repository_id}/knowledge/gaps")
def knowledge_gaps(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None, status_filter: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    run = _knowledge_run(db, repository_id, user, snapshot_id=snapshot_id)
    if not run:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}
    query = select(KnowledgeGap).where(KnowledgeGap.analysis_run_id == run.id)
    if status_filter:
        query = query.where(KnowledgeGap.status == status_filter)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(KnowledgeGap.severity, KnowledgeGap.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"id": g.id, "title": g.title, "category": g.category, "description": g.description, "affected_component": g.affected_component, "why_it_matters": g.why_it_matters, "recommended_question": g.recommended_question, "severity": g.severity, "confidence": g.confidence, "status": g.status, "evidence_references": g.evidence_references} for g in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/{repository_id}/knowledge/conflicts")
def knowledge_conflicts(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    run = _knowledge_run(db, repository_id, user, snapshot_id=snapshot_id)
    if not run:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}
    query = select(KnowledgeConflict).where(KnowledgeConflict.analysis_run_id == run.id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(KnowledgeConflict.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"id": c.id, "conflict_type": c.conflict_type, "claim_a": c.claim_a, "claim_b": c.claim_b, "evidence_a": c.evidence_a, "evidence_b": c.evidence_b, "confidence": c.confidence, "status": c.status, "possible_explanation": c.possible_explanation} for c in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/{repository_id}/knowledge/assumptions")
def knowledge_assumptions(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    run = _knowledge_run(db, repository_id, user, snapshot_id=snapshot_id)
    if not run:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}
    query = select(ProjectAssumption).where(ProjectAssumption.analysis_run_id == run.id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(ProjectAssumption.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"id": a.id, "description": a.description, "assumption_type": a.assumption_type, "evidence_level": a.evidence_level, "confidence": a.confidence, "verification_status": a.verification_status, "supporting_evidence": a.supporting_evidence, "verification_method": a.verification_method} for a in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/{repository_id}/knowledge/completeness")
def knowledge_completeness(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None):
    _connection(db, repository_id, user)
    snapshot = db.get(RepositorySnapshot, snapshot_id) if snapshot_id else db.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_connection_id == repository_id).order_by(RepositorySnapshot.created_at.desc()).limit(1))
    if not snapshot or snapshot.repository_connection_id != repository_id:
        raise NotFoundError("Repository snapshot not found.")
    rows = db.scalars(select(RepositoryFile).where(RepositoryFile.snapshot_id == snapshot.id)).all()
    paths = {row.path.lower() for row in rows}
    dims = [("project_purpose", ("readme.md",), "Look for a concise statement of intended users and outcomes."), ("architecture", ("architecture", "design"), "Document major modules and their supported relationships."), ("setup", ("contributing.md", "development.md", "install"), "Document local prerequisites and setup steps."), ("testing", ("test", "spec", "pytest.ini", "vitest"), "Explain how to run and interpret tests."), ("deployment", ("deploy", "dockerfile", "docker-compose", "workflow"), "Document deployment steps, configuration and recovery."), ("api", ("openapi", "swagger", "api.md"), "Document stable API contracts."), ("operations", ("runbook", "operations", "incident", "recovery"), "Document operational procedures and failure recovery."), ("decisions", ("adr", "decision", "architecture"), "Record technical rationale and alternatives.")]
    items = []
    for category, indicators, recommendation in dims:
        matches = sorted(path for path in paths if any(indicator in path for indicator in indicators))
        status_text = "well_documented" if len(matches) > 1 else "partially_documented" if matches else "not_found"
        items.append({"dimension": category, "status": status_text, "evidence_found": matches[:30], "sources_inspected": len(rows), "confidence": 0.62 if rows else 0.0, "recommended_improvement": recommendation, "limitation": "File presence is a discoverability signal, not proof that content is complete or current."})
    return {"snapshot_id": snapshot.id, "items": items, "aggregate_score": None, "note": "No aggregate score is shown; absence in this snapshot is not proof the knowledge does not exist."}


@router.get("/{repository_id}/knowledge/profile")
def successor_knowledge_profile(repository_id: uuid.UUID, user: CurrentUser, db: DbSession, snapshot_id: uuid.UUID | None = None):
    run = _knowledge_run(db, repository_id, user, snapshot_id=snapshot_id)
    if not run:
        return {"status": "not_started", "sections": []}
    rows = db.scalars(select(KnowledgeUnit).where(KnowledgeUnit.analysis_run_id == run.id).order_by(KnowledgeUnit.category, KnowledgeUnit.title).limit(200)).all()
    groups = {"project_fundamentals": {"project_context", "feature_description", "architecture_description"}, "development_knowledge": {"development_workflow", "dependency_requirement"}, "technical_decisions": {"technical_decision_context", "historical_change"}, "operational_knowledge": {"operational_procedure"}, "outstanding_context": {"reported_problem", "unresolved_question", "known_limitation", "implementation_context"}}
    sections = []
    for name, categories in groups.items():
        units = [u for u in rows if u.category in categories]
        section_evidence = []
        for unit in units[:25]:
            ev = db.scalars(select(KnowledgeEvidence).where(KnowledgeEvidence.knowledge_unit_id == unit.id).limit(5)).all()
            section_evidence.extend({"unit_id": str(unit.id), "title": unit.title, "evidence_level": unit.evidence_level, "source": e.source_location or e.source_name, "source_url": e.source_url, "quote": e.quote[:500]} for e in ev)
        sections.append({"section": name, "items": [{"id": str(u.id), "category": u.category, "title": u.title, "content": u.content, "evidence_level": u.evidence_level, "confidence": u.confidence} for u in units[:25]], "evidence": section_evidence, "status": "evidence_found" if units else "unknown"})
    gaps = db.scalars(select(KnowledgeGap).where(KnowledgeGap.analysis_run_id == run.id, KnowledgeGap.status.in_(["open", "under_review"])).limit(50)).all()
    sections.append({"section": "critical_unknowns", "items": [{"id": str(g.id), "title": g.title, "question": g.recommended_question, "confidence": g.confidence, "evidence": g.evidence_references} for g in gaps], "status": "evidence_found" if gaps else "not_identified"})
    return {"status": "ready", "analysis_id": run.id, "sections": sections, "generated_from": run.coverage}


@router.post("/{repository_id}/knowledge/search")
def search_repository_knowledge(repository_id: uuid.UUID, payload: dict, user: CurrentUser, db: DbSession):
    run = _knowledge_run(db, repository_id, user, snapshot_id=payload.get("snapshot_id"))
    query_text = str(payload.get("query", "")).strip()[:500]
    if len(query_text) < 2:
        raise ValidationAppError("Enter at least two characters to search repository knowledge.")
    if not run:
        return {"answer": "Unknown: knowledge analysis has not been run for this snapshot.", "items": [], "conflicts": [], "missing_information": True, "method": "keyword_fallback"}
    terms = [term for term in re.findall(r"[\w.-]{2,}", query_text.lower())[:12]]
    rows = db.scalars(select(KnowledgeUnit).where(KnowledgeUnit.analysis_run_id == run.id).limit(1000)).all()
    ranked = []
    for unit in rows:
        haystack = f"{unit.title} {unit.content}".lower()
        score = sum(haystack.count(term) * (3 if term in unit.title.lower() else 1) for term in terms)
        if score:
            ranked.append((score, unit))
    ranked.sort(key=lambda item: (-item[0], item[1].category, item[1].title))
    result_items = []
    for score, unit in ranked[:10]:
        evidence = db.scalars(select(KnowledgeEvidence).where(KnowledgeEvidence.knowledge_unit_id == unit.id).limit(5)).all()
        result_items.append({"id": unit.id, "title": unit.title, "content": unit.content, "category": unit.category, "evidence_level": unit.evidence_level, "confidence": unit.confidence, "relevance_score": score, "freshness": unit.freshness_status, "evidence": [{"source": e.source_name, "location": e.source_location, "source_url": e.source_url, "quote": e.quote, "source_timestamp": e.source_timestamp} for e in evidence]})
    conflicts = db.scalars(select(KnowledgeConflict).where(KnowledgeConflict.analysis_run_id == run.id, KnowledgeConflict.status == "open").limit(20)).all()
    relevant_conflicts = [{"id": c.id, "claim_a": c.claim_a, "claim_b": c.claim_b, "evidence_a": c.evidence_a, "evidence_b": c.evidence_b} for c in conflicts if any(term in f"{c.claim_a} {c.claim_b}".lower() for term in terms)]
    answer = "Evidence excerpts matched the query; inspect each citation before treating them as a verified answer." if result_items else "Unknown: the indexed evidence does not answer this query."
    return {"answer": answer, "items": result_items, "conflicts": relevant_conflicts, "observed_vs_inferred": "Each result is labeled with its evidence level.", "missing_information": not bool(result_items), "source_freshness": "Freshness is unverified for this snapshot run.", "method": "ranked keyword fallback; no embeddings are configured"}


@router.post("/{repository_id}/knowledge/gaps/{gap_id}/resolve")
def update_knowledge_gap(repository_id: uuid.UUID, gap_id: uuid.UUID, payload: dict, user: CurrentUser, db: DbSession):
    _connection(db, repository_id, user)
    gap = db.get(KnowledgeGap, gap_id)
    if not gap or gap.repository_id != repository_id:
        raise NotFoundError("Knowledge gap not found.")
    new_status = str(payload.get("status", "resolved"))
    if new_status not in {"under_review", "answered", "resolved", "dismissed", "open"}:
        raise ValidationAppError("Status must be open, under_review, answered, resolved, or dismissed.")
    gap.status = new_status
    db.commit()
    return {"id": gap.id, "status": gap.status}


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
