from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RepositoryValidateRequest(BaseModel):
    repository_url: str = Field(min_length=1, max_length=500)


class BranchInfo(BaseModel):
    name: str
    commit_sha: str
    protected: bool = False
    is_default: bool = False


class RepositoryMetadata(BaseModel):
    name: str
    owner: str
    description: str | None = None
    canonical_url: str
    default_branch: str
    visibility: str
    language: str | None = None
    languages: dict[str, int] = Field(default_factory=dict)
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pushed_at: datetime | None = None
    license: str | None = None


class RepositoryValidationResponse(BaseModel):
    valid: bool = True
    repository: RepositoryMetadata
    branches: list[BranchInfo]
    selected_branch: str


class RepositoryAnalyseRequest(BaseModel):
    repository_url: str = Field(min_length=1, max_length=500)
    branch: str | None = Field(default=None, max_length=200)


class RepositoryConnectionResponse(BaseModel):
    id: UUID
    project_id: UUID
    provider: str
    owner: str
    repository_name: str
    repository_url: str
    default_branch: str | None
    selected_branch: str | None
    visibility: str
    description: str | None
    language: str | None
    languages: dict[str, int]
    stars: int
    forks: int
    open_issues: int
    license_name: str | None
    repository_created_at: datetime | None
    repository_updated_at: datetime | None
    repository_pushed_at: datetime | None
    branches: list[dict]
    latest_snapshot: dict | None = None


class AnalysisStartedResponse(BaseModel):
    repository_id: UUID
    analysis_run_id: UUID
    status: str
    stage: str


class SnapshotProgressResponse(BaseModel):
    id: UUID
    repository_id: UUID
    branch: str
    commit_sha: str | None
    status: str
    stage: str
    tree_complete: bool
    files_discovered: int
    files_processed: int
    files_skipped: int
    commits_processed: int
    issues_processed: int
    pull_requests_processed: int
    warnings: list[str]
    error_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None


class RepositoryPage(BaseModel):
    items: list[dict]
    page: int
    page_size: int
    total: int
