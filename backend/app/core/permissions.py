"""Role hierarchy and permission checks.

All authorisation is enforced here on the server. The frontend never decides
what a user may do.
"""

from __future__ import annotations

from app.core.errors import ForbiddenError
from app.models.enums import WorkspaceRole

_ROLE_RANK: dict[WorkspaceRole, int] = {
    WorkspaceRole.VIEWER: 1,
    WorkspaceRole.MEMBER: 2,
    WorkspaceRole.ADMIN: 3,
    WorkspaceRole.OWNER: 4,
}

#: Minimum role required to read workspace resources.
READ_ROLES = (WorkspaceRole.VIEWER, WorkspaceRole.MEMBER, WorkspaceRole.ADMIN, WorkspaceRole.OWNER)
#: Minimum role required to create/modify projects and ingest sources.
WRITE_ROLES = (WorkspaceRole.MEMBER, WorkspaceRole.ADMIN, WorkspaceRole.OWNER)
#: Minimum role required to delete projects or connect integrations.
ADMIN_ROLES = (WorkspaceRole.ADMIN, WorkspaceRole.OWNER)


def role_rank(role: WorkspaceRole) -> int:
    return _ROLE_RANK.get(role, 0)


def has_at_least(role: WorkspaceRole | None, required: WorkspaceRole) -> bool:
    if role is None:
        return False
    return role_rank(role) >= role_rank(required)


def ensure_role(
    role: WorkspaceRole | None,
    allowed: tuple[WorkspaceRole, ...],
    *,
    action: str,
) -> None:
    if role is None or role not in allowed:
        raise ForbiddenError(
            f"Your workspace role does not permit this action: {action}.",
            details={"required_roles": [item.value for item in allowed]},
        )
