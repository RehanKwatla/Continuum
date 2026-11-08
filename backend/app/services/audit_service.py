"""Audit logging service (append-only)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog

logger = logging.getLogger("continuum.audit")


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
