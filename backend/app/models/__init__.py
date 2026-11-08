"""ORM models package — importing it registers every table on ``Base.metadata``."""

from app.models.audit import AuditLog
from app.models.claim import Claim
from app.models.enums import (
    AccessLabel,
    ClaimStatus,
    ClaimType,
    GitHubSubjectType,
    ProcessingStatus,
    ProjectStatus,
    SourceType,
    VerificationVerdict,
    WorkspaceRole,
)
from app.models.evidence import Evidence
from app.models.github_connection import GitHubConnection
from app.models.project import Project
from app.models.project_repository import ProjectRepository
from app.models.source import Source
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

__all__ = [
    "AccessLabel",
    "AuditLog",
    "Claim",
    "ClaimStatus",
    "ClaimType",
    "Evidence",
    "GitHubConnection",
    "GitHubSubjectType",
    "ProcessingStatus",
    "Project",
    "ProjectRepository",
    "ProjectStatus",
    "Source",
    "SourceType",
    "User",
    "VerificationVerdict",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceRole",
]
