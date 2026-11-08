"""GitHub OAuth connection and repository ingestion endpoints.

Security notes:
  * the OAuth access token is exchanged and stored **server-side only** and is
    Fernet-encrypted at rest — it is never returned to the browser;
  * the ``state`` parameter is a short-lived signed JWT bound to the local user
    id, giving CSRF protection without a server session;
  * when the integration is not configured the endpoints return a clearly
    labelled boundary (503 with remediation steps) instead of fake data.
"""

from __future__ import annotations

import logging
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Query, status
from fastapi.responses import RedirectResponse

from app.core.dependencies import (
    AppSettings,
    CurrentUser,
    DbSession,
    resolve_project_access,
)
from app.core.errors import AppError
from app.models.enums import WorkspaceRole
from app.schemas.github import (
    GitHubConnectResponse,
    GitHubImportBoundary,
    GitHubImportRequest,
    GitHubImportResponse,
    GitHubRepositoryDetail,
    GitHubRepositoryListResponse,
    GitHubRepositorySummary,
    GitHubStatusResponse,
)
from app.services.github_service import MISSING_CONFIGURATION_HELP, GitHubService

logger = logging.getLogger("continuum.api.github")

router = APIRouter(tags=["github"])


@router.get("/github/status", response_model=GitHubStatusResponse, summary="GitHub connection status")
def github_status(user: CurrentUser, db: DbSession) -> GitHubStatusResponse:
    return GitHubService(db).status(user)


@router.get(
    "/github/boundary",
    response_model=GitHubImportBoundary,
    summary="Explicit integration boundary when GitHub is not configured",
)
def github_boundary(settings: AppSettings) -> GitHubImportBoundary:
    configured = settings.github_oauth_configured
    return GitHubImportBoundary(
        configured=configured,
        reason=(
            "GitHub OAuth is configured."
            if configured
            else "GitHub OAuth credentials are absent; repository import is inert."
        ),
        remediation=[] if configured else MISSING_CONFIGURATION_HELP,
    )


@router.post(
    "/github/connect",
    response_model=GitHubConnectResponse,
    summary="Begin the GitHub OAuth flow (returns the authorisation URL)",
)
def github_connect(user: CurrentUser, db: DbSession) -> GitHubConnectResponse:
    authorize_url, state = GitHubService(db).start_connect(user)
    return GitHubConnectResponse(authorize_url=authorize_url, state=state)


@router.get(
    "/github/callback",
    summary="GitHub OAuth redirect target",
    response_class=RedirectResponse,
)
def github_callback(
    db: DbSession,
    settings: AppSettings,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None, alias="state"),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Browser-facing callback. Always redirects back to the frontend."""
    frontend = settings.github_oauth_frontend_redirect

    if error:
        return RedirectResponse(f"{frontend}?github=error&reason={quote(error)}")
    if not code or not state:
        return RedirectResponse(f"{frontend}?github=error&reason=missing_parameters")

    try:
        GitHubService(db).complete_connect(state=state, code=code)
    except AppError as exc:
        logger.warning("GitHub OAuth callback failed: %s", exc.code)
        return RedirectResponse(f"{frontend}?github=error&reason={quote(exc.code)}")

    return RedirectResponse(f"{frontend}?github=connected")


@router.post(
    "/github/disconnect",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove the stored GitHub connection",
)
def github_disconnect(user: CurrentUser, db: DbSession) -> None:
    GitHubService(db).disconnect(user)


@router.get(
    "/github/repositories",
    response_model=GitHubRepositoryListResponse,
    summary="List repositories the caller is authorised to read",
)
def list_github_repositories(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=300),
) -> GitHubRepositoryListResponse:
    items = GitHubService(db).list_repositories(user, limit=limit)
    return GitHubRepositoryListResponse(
        items=items, total=len(items), truncated=len(items) >= limit
    )


@router.get(
    "/github/repository",
    response_model=GitHubRepositoryDetail,
    summary="Repository metadata for the selection screen",
)
def github_repository_detail(
    user: CurrentUser,
    db: DbSession,
    full_name: str = Query(min_length=3, max_length=300, description="'owner/name'"),
) -> GitHubRepositoryDetail:
    detail = GitHubService(db).get_repository_detail(user, full_name)
    repository: GitHubRepositorySummary = detail["repository"]
    return GitHubRepositoryDetail(
        repository=repository,
        readme_present=bool(detail.get("readme_present")),
        default_branch_sha=detail.get("default_branch_sha"),
        open_issues=detail.get("open_issues"),
    )


@router.post(
    "/projects/{project_id}/github/import",
    response_model=GitHubImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import commits, issues, pull requests and documents from a repository",
)
def import_github_repository(
    project_id: uuid.UUID,
    payload: GitHubImportRequest,
    user: CurrentUser,
    db: DbSession,
) -> GitHubImportResponse:
    project, _ = resolve_project_access(
        db, project_id=project_id, user=user, required_role=WorkspaceRole.MEMBER
    )
    return GitHubService(db).import_repository(project, payload, user=user)
