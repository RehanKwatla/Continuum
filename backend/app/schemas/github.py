"""GitHub integration schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.project import RepositoryRead
from app.schemas.source import IngestionResult


class GitHubConnectResponse(BaseModel):
    authorize_url: str = Field(description="GitHub authorisation URL to open in the browser.")
    state: str = Field(description="Opaque, signed CSRF state value.")


class GitHubTokenConnectRequest(BaseModel):
    token: str = Field(min_length=10, max_length=500, description="GitHub Personal Access Token (PAT).")


class GitHubStatusResponse(BaseModel):
    configured: bool = Field(description="True when server-side OAuth credentials are present.")
    connected: bool = False
    login: str | None = None
    avatar_url: str | None = None
    github_user_id: str | None = None
    scopes: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None
    message: str | None = None


class GitHubRepositorySummary(BaseModel):
    id: str
    full_name: str
    name: str
    owner: str
    private: bool = False
    description: str | None = None
    default_branch: str | None = None
    html_url: str | None = None
    language: str | None = None
    stars: int = 0
    updated_at: datetime | None = None


class GitHubRepositoryListResponse(BaseModel):
    items: list[GitHubRepositorySummary]
    total: int
    truncated: bool = False


class GitHubImportRequest(BaseModel):
    repository: str = Field(
        min_length=3, max_length=300, description="Repository in 'owner/name' form."
    )
    include_commits: bool = True
    include_issues: bool = True
    include_pull_requests: bool = True
    include_readme: bool = True
    include_files: bool = Field(
        default=False,
        description="Import permitted text files from the repository root and docs folder.",
    )
    include_changed_files: bool = Field(
        default=False,
        description=(
            "Fetch the changed-file list for each commit/PR. Costs one extra GitHub API "
            "request per record, so it is disabled by default."
        ),
    )
    max_items: int = Field(default=50, ge=1, le=200, description="Per-category item cap.")


class GitHubImportResponse(BaseModel):
    repository: RepositoryRead
    imported: int
    duplicates: int
    skipped: int
    failed: int
    results: list[IngestionResult] = Field(default_factory=list)


class GitHubImportBoundary(BaseModel):
    """Explicit, clearly labelled gap when GitHub is not configured."""

    configured: bool
    reason: str
    remediation: list[str] = Field(default_factory=list)


class GitHubRepositoryDetail(BaseModel):
    repository: GitHubRepositorySummary
    readme_present: bool = False
    default_branch_sha: str | None = None
    open_issues: int | None = None
    project_id: uuid.UUID | None = None
