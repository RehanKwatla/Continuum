"""Pydantic v2 schema package (API contracts + Phase 3 AI contracts)."""

from app.schemas.auth import AuthSessionResponse, UserProfile
from app.schemas.claim import (
    AI_ASSIGNABLE_STATUSES,
    HUMAN_ONLY_STATUSES,
    Claim,
    ClaimExtractionResult,
    SourceSpanRef,
    Verification,
    assert_ai_assignable_status,
)
from app.schemas.common import ErrorDetail, ErrorResponse, Page, PageMeta, build_page_meta
from app.schemas.evidence import EvidenceBundle, EvidenceCreate, EvidenceRead
from app.schemas.github import (
    GitHubConnectResponse,
    GitHubImportRequest,
    GitHubImportResponse,
    GitHubRepositorySummary,
    GitHubStatusResponse,
)
from app.schemas.project import ProjectCreate, ProjectRead, ProjectSummary, ProjectUpdate
from app.schemas.source import (
    IngestionResult,
    SourceListResponse,
    SourceRead,
    SourceSummary,
    UploadResponse,
)
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberRead,
    WorkspaceRead,
    WorkspaceSummary,
)

__all__ = [
    "AI_ASSIGNABLE_STATUSES",
    "HUMAN_ONLY_STATUSES",
    "AuthSessionResponse",
    "Claim",
    "ClaimExtractionResult",
    "ErrorDetail",
    "ErrorResponse",
    "EvidenceBundle",
    "EvidenceCreate",
    "EvidenceRead",
    "GitHubConnectResponse",
    "GitHubImportRequest",
    "GitHubImportResponse",
    "GitHubRepositorySummary",
    "GitHubStatusResponse",
    "IngestionResult",
    "Page",
    "PageMeta",
    "ProjectCreate",
    "ProjectRead",
    "ProjectSummary",
    "ProjectUpdate",
    "SourceListResponse",
    "SourceRead",
    "SourceSpanRef",
    "SourceSummary",
    "UploadResponse",
    "UserProfile",
    "Verification",
    "WorkspaceCreate",
    "WorkspaceMemberRead",
    "WorkspaceRead",
    "WorkspaceSummary",
    "assert_ai_assignable_status",
    "build_page_meta",
]
