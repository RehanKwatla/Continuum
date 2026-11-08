"""Audit logging service (append-only).

Two responsibilities live here:

* :func:`record` — the general-purpose append helper used across the
  application (projects, sources, uploads, …). It never raises: a failure to
  audit must not fail the user's request.
* :func:`project_audit_trail` — the Phase 4 §15 read model. Phase 4 records
  stamp the owning ``project_id`` into the entry's metadata so a project's
  history can be listed without leaking another project's (or another
  workspace's) activity.

Nothing in the application updates or deletes an :class:`AuditLog` row.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.project import Project

logger = logging.getLogger("continuum.audit")

#: Audit actions that belong to the review → approval → handover workflow.
PHASE4_ACTIONS: frozenset[str] = frozenset(
    {
        "claim_approved",
        "claim_rejected",
        "claim_edited",
        "claim_clarification_requested",
        "claim_evidence_requested",
        "conflict_resolved",
        "handover_generated",
        "handover_edited",
        "handover_version_created",
        "handover_submitted",
        "handover_approved",
        "handover_published",
        "handover_archived",
        "handover_exported",
        "handover_accessed",
    }
)


def record(
    db: Session,
    *,
    action: str,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog | None:
    """Append an audit entry.

    Never raises: a failure to audit must not fail the user's request, but it
    is logged loudly.
    """
    entry = AuditLog(
        action=action,
        user_id=user_id,
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_id=resource_id,
        meta=metadata or {},
    )
    try:
        db.add(entry)
        db.commit()
    except Exception:  # pragma: no cover - audit must never break a request
        logger.exception("Failed to write audit log for action %s", action)
        db.rollback()
        return None
    return entry


def project_audit_trail(
    db: Session,
    project: Project,
    *,
    actions: list[str] | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AuditLog], int]:
    """List the audit entries recorded for one project, newest first."""
    filters = [
        AuditLog.workspace_id == project.workspace_id,
        AuditLog.meta["project_id"].astext == str(project.id),
    ]
    if actions:
        filters.append(AuditLog.action.in_(actions))

    total = int(
        db.execute(select(func.count()).select_from(AuditLog).where(*filters)).scalar_one()
    )
    rows = list(
        db.execute(
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).scalars().all()
    )
    return rows, total


__all__ = ["PHASE4_ACTIONS", "record", "project_audit_trail"]
