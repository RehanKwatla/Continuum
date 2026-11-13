"""Deterministic, snapshot-scoped successor handover assembly (Stage 6).

This service only organizes persisted Stage 1–5 records. Repository text is
treated as data; no repository instruction is executed or followed.
"""
from __future__ import annotations

import uuid
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.models.code_intelligence import ArchitectureComponent, CodeAnalysisRun, ExternalDependency
from app.models.git_history import CommitInsight, HistoryAnalysisRun
from app.models.repository_intelligence import (
    IssueRecord, PullRequestRecord, RepositoryConnection, RepositorySnapshot,
)
from app.models.repository_knowledge import (
    KnowledgeAnalysisRun, KnowledgeEvidence, KnowledgeGap, KnowledgeUnit,
)
from app.models.handover import SuccessorHandoverPackage

ROLE_FOCUS: dict[str, tuple[str, ...]] = {
    "backend_developer": ("backend", "api", "database", "service", "integration", "security", "test", "dependency", "gap", "decision"),
    "frontend_developer": ("frontend", "ui", "component", "route", "state", "build", "test", "dependency", "gap"),
    "full_stack_developer": ("architecture", "api", "database", "frontend", "backend", "integration", "workflow", "gap", "decision"),
    "ml_ai_engineer": ("model", "ai", "ml", "data", "embedding", "retrieval", "evaluation", "inference", "gap"),
    "devops_infrastructure_engineer": ("deployment", "infrastructure", "database", "environment", "worker", "monitoring", "security", "dependency", "gap"),
    "project_maintainer": ("architecture", "decision", "issue", "risk", "contributor", "documentation", "gap", "conflict"),
    "custom": (),
}


def prioritize_knowledge(items: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    """Stable, explainable role ordering; it changes ordering, never facts."""
    focus = ROLE_FOCUS.get(role, tuple(re.findall(r"[a-z0-9]+", role.lower())))
    return sorted(
        items,
        key=lambda item: (
            not any(token in f"{item.get('category', '')} {item.get('title', '')} {item.get('content', '')}".lower() for token in focus),
            -float(item.get("confidence", 0)),
            str(item.get("title", "")),
        ),
    )


def _latest(db: Session, model: Any, snapshot_id: uuid.UUID):
    return db.scalar(select(model).where(model.snapshot_id == snapshot_id).order_by(model.created_at.desc()).limit(1))


def build_successor_handover(db: Session, project_id: uuid.UUID, role: str = "project_maintainer") -> dict[str, Any]:
    role = role.strip().lower()
    if not role or len(role) > 40:
        raise ValidationAppError("Successor role must contain 1–40 characters.")
    connection = db.scalar(select(RepositoryConnection).where(RepositoryConnection.project_id == project_id).order_by(RepositoryConnection.created_at.desc()).limit(1))
    if connection is None:
        raise NotFoundError("Connect and ingest a repository before generating a successor handover.")
    snapshot = db.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_connection_id == connection.id).order_by(RepositorySnapshot.created_at.desc()).limit(1))
    if snapshot is None:
        raise NotFoundError("No repository snapshot is available for this project.")
    if str(snapshot.ingestion_status) not in {"completed", "partially_completed", "RepositoryIngestionStatus.COMPLETED", "RepositoryIngestionStatus.PARTIALLY_COMPLETED"}:
        raise ValidationAppError("Handover assembly requires a completed repository snapshot.")

    code_run = _latest(db, CodeAnalysisRun, snapshot.id)
    history_run = _latest(db, HistoryAnalysisRun, snapshot.id)
    knowledge_run = _latest(db, KnowledgeAnalysisRun, snapshot.id)
    units = db.scalars(select(KnowledgeUnit).where(KnowledgeUnit.analysis_run_id == knowledge_run.id).order_by(KnowledgeUnit.category, KnowledgeUnit.title).limit(500)).all() if knowledge_run else []
    evidence_by_unit: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if units:
        for item in db.scalars(select(KnowledgeEvidence).where(KnowledgeEvidence.knowledge_unit_id.in_([u.id for u in units])).limit(2000)).all():
            evidence_by_unit.setdefault(item.knowledge_unit_id, []).append({
                "source_type": item.source_type, "source_name": item.source_name,
                "file_path": item.file_path, "line_start": item.line_start,
                "line_end": item.line_end, "url": item.source_url,
            })

    def ref(kind: str, identifier: Any, label: str, url: str | None = None) -> dict[str, Any]:
        return {"type": kind, "id": str(identifier), "label": label, "url": url}

    knowledge = [{
        "id": str(unit.id), "category": unit.category, "title": unit.title,
        "content": unit.content, "evidence_level": unit.evidence_level,
        "confidence": unit.confidence, "freshness": unit.freshness_status,
        "evidence": evidence_by_unit.get(unit.id, []),
    } for unit in units]
    knowledge = prioritize_knowledge(knowledge, role)

    components = db.scalars(select(ArchitectureComponent).where(ArchitectureComponent.analysis_run_id == code_run.id).order_by(ArchitectureComponent.component_name).limit(200)).all() if code_run else []
    dependencies = db.scalars(select(ExternalDependency).where(ExternalDependency.analysis_run_id == code_run.id).order_by(ExternalDependency.package_name).limit(200)).all() if code_run else []
    commits = db.scalars(select(CommitInsight).where(CommitInsight.snapshot_id == snapshot.id).order_by(CommitInsight.created_at.desc()).limit(30)).all() if history_run else []
    gaps = db.scalars(select(KnowledgeGap).where(KnowledgeGap.analysis_run_id == knowledge_run.id, KnowledgeGap.status == "open").order_by(KnowledgeGap.severity, KnowledgeGap.title).limit(100)).all() if knowledge_run else []
    issues = db.scalars(select(IssueRecord).where(IssueRecord.repository_connection_id == connection.id, IssueRecord.state == "open").order_by(IssueRecord.issue_number.desc()).limit(100)).all()
    prs = db.scalars(select(PullRequestRecord).where(PullRequestRecord.repository_connection_id == connection.id, PullRequestRecord.state == "open").order_by(PullRequestRecord.pr_number.desc()).limit(100)).all()

    tasks: list[dict[str, Any]] = []
    for issue in issues:
        tasks.append({"id": f"issue:{issue.issue_number}", "title": issue.title, "description": issue.description or "Review issue details and determine scope.", "category": "open_issue", "priority": "high" if any(word in issue.title.lower() for word in ("security", "broken", "outage", "data loss")) else "medium", "status": "suggested", "evidence": [ref("issue", issue.issue_number, f"Issue #{issue.issue_number}", issue.url)]})
    for pr in prs:
        tasks.append({"id": f"pr:{pr.pr_number}", "title": f"Review open pull request: {pr.title}", "description": pr.description or "Review the proposed changes and checks before deciding whether to merge.", "category": "open_pull_request", "priority": "medium", "status": "suggested", "evidence": [ref("pull_request", pr.pr_number, f"Pull request #{pr.pr_number}", pr.url)]})
    for gap in gaps:
        tasks.append({"id": f"gap:{gap.id}", "title": gap.title, "description": gap.recommended_question, "category": "knowledge_gap", "priority": "critical" if gap.severity == "critical" else "high" if gap.severity == "high" else "medium", "status": "blocked", "affected_component": gap.affected_component, "reason": gap.why_it_matters, "evidence": gap.evidence_references or []})

    section_items = [
        {"key": "project_overview", "title": "Project overview", "items": [{"text": connection.description or f"Repository {connection.owner}/{connection.repository_name}", "evidence_level": "observed", "evidence": [ref("snapshot", snapshot.id, f"Snapshot {snapshot.commit_sha or snapshot.branch}")]}]},
        {"key": "architecture", "title": "System architecture", "items": [{"text": f"{c.component_name}: {c.category}", "evidence_level": "inferred", "evidence": [ref("code_analysis", code_run.id, f"Code analysis ({c.confidence} confidence)")] + [ref("file", p, p) for p in (c.file_paths or [])[:10]]} for c in components]},
        {"key": "development_setup", "title": "Development setup", "items": [{"text": f"Detected dependency: {d.package_name} {d.declared_version or ''} ({d.ecosystem}) from {d.manifest_path}", "evidence_level": "observed", "evidence": [ref("file", d.manifest_path, d.manifest_path)]} for d in dependencies]},
        {"key": "technical_decisions", "title": "Technical decisions and history", "items": [{"text": c.summary, "evidence_level": "inferred", "evidence": [ref("commit", c.commit_sha, c.commit_sha[:12])]} for c in commits]},
        {"key": "critical_knowledge", "title": "Critical knowledge", "items": knowledge},
        {"key": "outstanding_work", "title": "Outstanding work", "items": tasks},
    ]
    has_decisions = bool(commits) or any(u["category"] in {"decision", "historical_decision"} for u in knowledge)
    has_operations = any(any(x in f"{u['category']} {u['title']}".lower() for x in ("deploy", "environment", "operation")) for u in knowledge)
    raw_dimensions = {
        "architecture": ("ready" if components else "unable_to_assess", bool(components)),
        "development_setup": ("ready" if dependencies or knowledge else "unable_to_assess", bool(dependencies or knowledge)),
        "technical_decisions": ("ready" if has_decisions else "unable_to_assess", has_decisions),
        "operational": ("ready" if has_operations else "unable_to_assess", has_operations),
        "outstanding_work": ("ready" if tasks else "unable_to_assess", bool(tasks)),
        "dependencies": ("ready" if dependencies else "unable_to_assess", bool(dependencies)),
        "knowledge_gaps": ("not_ready" if gaps else "ready" if knowledge_run else "unable_to_assess", bool(knowledge_run)),
        "evidence": ("ready" if any(bool(u["evidence"]) for u in knowledge) else "unable_to_assess", bool(knowledge_run)),
    }
    role_dimensions = {
        "frontend_developer": {"architecture", "development_setup", "outstanding_work", "dependencies", "knowledge_gaps", "evidence"},
        "backend_developer": {"architecture", "development_setup", "technical_decisions", "outstanding_work", "dependencies", "knowledge_gaps", "evidence"},
        "devops_infrastructure_engineer": {"architecture", "development_setup", "operational", "outstanding_work", "dependencies", "knowledge_gaps", "evidence"},
        "ml_ai_engineer": {"architecture", "development_setup", "technical_decisions", "operational", "outstanding_work", "dependencies", "knowledge_gaps", "evidence"},
    }
    applicable = role_dimensions.get(role, set(raw_dimensions))
    dimensions = [{"dimension": key, "status": raw_dimensions[key][0] if key in applicable else "not_applicable", "explanation": "Supported by snapshot-scoped persisted analysis." if raw_dimensions[key][0] == "ready" else "Unresolved knowledge gaps have been found." if raw_dimensions[key][0] == "not_ready" else "No supporting record was found in the selected snapshot analysis." if key in applicable else "Not a primary readiness requirement for this successor role."} for key in raw_dimensions]
    active_statuses = [status for key, (status, _assessed) in raw_dimensions.items() if key in applicable]
    overall = "not_ready" if "not_ready" in active_statuses else "ready" if active_statuses and all(item == "ready" for item in active_statuses) else "partially_ready" if any(item == "ready" for item in active_statuses) else "unable_to_assess"
    phase_specs = [("orientation", "Project orientation", "Understand purpose, major components, and dependencies", ["project_overview", "architecture"]), ("environment", "Development environment", "Inspect discovered manifests and setup evidence; confirm missing runtime steps from project documentation", ["development_setup"]), ("codebase", "Codebase familiarization", "Trace a component and its recorded dependencies", ["architecture", "critical_knowledge"]), ("history", "Historical context", "Review significant changes and linked commit evidence", ["technical_decisions"]), ("work", "Outstanding work", "Triage open issues, pull requests, and unresolved knowledge gaps", ["outstanding_work"]), ("contribution", "Independent contribution", "Choose a starter task and define its verification before implementation", ["outstanding_work"])]
    onboarding = [{"phase": phase, "title": title, "objective": objective, "related_sections": related, "status": "not_started", "completion_criteria": "Successor confirms completion; opening this handover alone does not mark this step complete."} for phase, title, objective, related in phase_specs]
    return {
        "project_id": str(project_id), "repository_id": str(connection.id), "snapshot_id": str(snapshot.id), "snapshot_commit": snapshot.commit_sha, "snapshot_branch": snapshot.branch,
        "role": role, "generated_at": datetime.now(timezone.utc).isoformat(), "generated_from": {"code_analysis_run_id": str(code_run.id) if code_run else None, "history_analysis_run_id": str(history_run.id) if history_run else None, "knowledge_analysis_run_id": str(knowledge_run.id) if knowledge_run else None},
        "source_coverage": {"snapshot_status": str(snapshot.ingestion_status), "files_processed": snapshot.files_processed, "files_discovered": snapshot.files_discovered, "has_code_analysis": code_run is not None, "has_history_analysis": history_run is not None, "has_knowledge_analysis": knowledge_run is not None, "knowledge_unit_count": len(units)},
        "sections": section_items, "tasks": tasks, "readiness": {"status": overall, "dimensions": dimensions, "blockers": [{"title": g.title, "description": g.description, "evidence": g.evidence_references or []} for g in gaps]},
        "onboarding": onboarding, "limitations": ["This package is assembled deterministically from persisted analyses; no generated statement is treated as human-verified.", "Setup commands and environment variables are omitted unless present in repository evidence.", "Task lifecycle, reviewer edits, and approvals remain in the existing successor and handover review workflows."],
    }


def persist_successor_package(db: Session, content: dict[str, Any], *, user_id: uuid.UUID, previous: SuccessorHandoverPackage | None = None) -> SuccessorHandoverPackage:
    """Append a package revision; never mutate an existing snapshot or approval."""
    role = str(content["role"])
    project_id = uuid.UUID(content["project_id"])
    latest = db.scalar(
        select(SuccessorHandoverPackage)
        .where(SuccessorHandoverPackage.project_id == project_id, SuccessorHandoverPackage.successor_role == role)
        .order_by(SuccessorHandoverPackage.version_number.desc()).limit(1)
    )
    row = SuccessorHandoverPackage(
        project_id=project_id,
        repository_id=uuid.UUID(content["repository_id"]),
        snapshot_id=uuid.UUID(content["snapshot_id"]),
        previous_package_id=previous.id if previous else (latest.id if latest else None),
        successor_role=role,
        version_number=(latest.version_number + 1) if latest else 1,
        status="draft",
        content=content,
        source_run_ids=content.get("generated_from", {}),
        created_by_id=user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def apply_human_edits(original: dict[str, Any], sections: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply reviewer-editable fields while protecting evidence provenance.

    Text changes invalidate attached evidence; a reviewer must explicitly
    re-check and regenerate from a source before it can be cited again.
    """
    updated = dict(original)
    original_sections = {section.get("key"): section for section in original.get("sections", [])}
    saved_sections: list[dict[str, Any]] = []
    for section in sections[:20]:
        key = str(section.get("key", ""))
        prior_section = original_sections.get(key)
        if not prior_section:
            continue
        prior_items = prior_section.get("items", [])
        next_items = []
        for index, item in enumerate(section.get("items", [])[:500]):
            prior = prior_items[index] if index < len(prior_items) else None
            limits = {"text": 8000, "content": 8000, "title": 500, "description": 4000}
            allowed = {field: item[field][:limits[field]] for field in limits if isinstance(item.get(field), str)}
            if prior is None:
                next_items.append({**allowed, "evidence_level": "unknown", "evidence": [], "reviewer_authored": True})
                continue
            prior_copy = dict(prior)
            prior_text = {field: prior.get(field) for field in ("text", "content", "title", "description") if field in prior}
            edited = any(field in allowed and allowed[field] != prior.get(field) for field in allowed)
            prior_copy.update(allowed)
            if edited:
                prior_copy["original_text"] = prior_text
                prior_copy["evidence_level"] = "reviewer_edited_unverified"
                prior_copy["evidence"] = []
            next_items.append(prior_copy)
        saved_sections.append({"key": key, "title": str(section.get("title") or prior_section.get("title", "Section")), "items": next_items})
    updated["sections"] = saved_sections

    original_tasks = {str(task.get("id")): task for task in original.get("tasks", [])}
    saved_tasks = []
    allowed_statuses = {"suggested", "accepted", "in_progress", "blocked", "completed", "dismissed"}
    allowed_priorities = {"critical", "high", "medium", "low"}
    for task in tasks[:500]:
        task_id = str(task.get("id", ""))
        prior = original_tasks.get(task_id)
        allowed = {field: task[field][:500 if field == "title" else 4000] if field in {"title", "description"} else task[field] for field in ("title", "description", "status", "priority") if isinstance(task.get(field), str)}
        if allowed.get("status") not in allowed_statuses and "status" in allowed:
            allowed.pop("status")
        if allowed.get("priority") not in allowed_priorities and "priority" in allowed:
            allowed.pop("priority")
        if prior is None:
            saved_tasks.append({**allowed, "id": task_id or uuid.uuid4().hex, "evidence": [], "reviewer_authored": True})
            continue
        prior_copy = dict(prior)
        edited_fact = any(field in allowed and allowed[field] != prior.get(field) for field in ("title", "description"))
        prior_copy.update(allowed)
        if edited_fact:
            prior_copy["original_text"] = {field: prior.get(field) for field in ("title", "description") if field in prior}
            prior_copy["evidence"] = []
            prior_copy["evidence_level"] = "reviewer_edited_unverified"
        saved_tasks.append(prior_copy)
    updated["tasks"] = saved_tasks
    return updated
