"""Dashboard aggregate endpoint — real database numbers, never mocked."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.dependencies import CurrentUser, DbSession
from app.core.errors import ForbiddenError, NotFoundError, RateLimitError, UpstreamError
from app.schemas.dashboard import DashboardStats
from app.services.public_github import GitHubApiError, GitHubPublicConnector
from app.services.project_service import ProjectService

router = APIRouter(tags=["dashboard"])
logger = logging.getLogger("continuum.dashboard")


class RepositoryActivityCommit(BaseModel):
    sha: str
    committed_at: datetime
    message: str = Field(max_length=160)


class RepositoryActivityResponse(BaseModel):
    repository_url: str
    branch: str
    sampled_commits: int
    sample_limit: int
    note: str
    commits: list[RepositoryActivityCommit]


@router.get("/dashboard", response_model=DashboardStats, summary="Workspace dashboard totals")
def read_dashboard(user: CurrentUser, db: DbSession) -> DashboardStats:
    return ProjectService(db).dashboard(user)


@router.get(
    "/dashboard/repository-activity",
    response_model=RepositoryActivityResponse,
    summary="Recent commit activity for the Continuum repository",
)
def read_repository_activity(user: CurrentUser) -> RepositoryActivityResponse:
    """Return real commit timestamps for the public Continuum repository.

    The requested repository is fixed server-side. GitHub credentials, when
    configured, remain on the backend; no user-provided host or repository can
    turn this endpoint into an arbitrary outbound request.
    """
    owner, name, limit = "RehanKwatla", "Continuum", 100
    connector = GitHubPublicConnector()
    try:
        branch = connector.get_default_branch(owner, name)
        if not branch:
            raise NotFoundError("The Continuum repository has no default branch.")
        raw_commits = connector.list_commits(owner, name, branch, limit=limit)
        commits = []
        for item in raw_commits[:limit]:
            commit_data = item.get("commit") or {}
            committer = commit_data.get("committer") or {}
            author = commit_data.get("author") or {}
            committed_at = committer.get("date") or author.get("date")
            if not committed_at:
                continue
            commits.append(RepositoryActivityCommit(
                sha=str(item.get("sha", ""))[:64],
                committed_at=committed_at,
                message=" ".join(str(commit_data.get("message", "")).split())[:160],
            ))
        return RepositoryActivityResponse(
            repository_url=f"https://github.com/{owner}/{name}",
            branch=str(branch),
            sampled_commits=len(commits),
            sample_limit=limit,
            note="Counts use at most the 100 newest commits returned by GitHub; older history may fall outside this sample.",
            commits=commits,
        )
    except GitHubApiError as exc:
        details = {
            "retry_after_seconds": exc.retry_after_seconds,
            "retry_at": exc.retry_at,
            "upstream_request_id": exc.request_id,
        }
        if exc.status == 429 or exc.code == "github_rate_limited":
            raise RateLimitError(str(exc), code="github_rate_limited", details=details) from exc
        if exc.status == 404:
            raise NotFoundError("The public Continuum repository could not be found.", code=exc.code) from exc
        if exc.status in {401, 403}:
            raise ForbiddenError("GitHub did not allow access to the public Continuum repository.", code=exc.code, details=details) from exc
        logger.warning("Dashboard repository activity unavailable code=%s request_id=%s", exc.code, exc.request_id)
        raise UpstreamError("GitHub commit activity is temporarily unavailable.", code=exc.code, status_code=503, details=details) from exc
    finally:
        connector.close()
