"""GitHub OAuth + REST ingestion service.

Design rules enforced here:
  * the OAuth access token never reaches frontend JavaScript;
  * tokens are Fernet-encrypted before being stored;
  * OAuth ``state`` is a short-lived signed value that binds the callback to a
    specific authenticated user (CSRF protection);
  * rate limits and permission errors are surfaced as explicit, typed errors
    rather than silent failures;
  * no repository is cloned and no private repository is read without the
    user's own authorisation.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TypeVar
from urllib.parse import urlencode

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from github import Auth, Github, GithubException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    AuthError,
    NotConfiguredError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
)
from app.models.enums import AccessLabel, ProcessingStatus, SourceType
from app.models.project import Project
from app.models.user import User
from app.repositories.github import GitHubRepository
from app.repositories.projects import ProjectsRepository
from app.schemas.github import (
    GitHubImportRequest,
    GitHubImportResponse,
    GitHubRepositorySummary,
    GitHubStatusResponse,
)
from app.schemas.source import IngestionResult
from app.services import audit_service
from app.services.ingestion_service import IngestionService

logger = logging.getLogger("continuum.github")

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_USER_URL = "https://api.github.com/user"

#: OAuth scopes requested. ``repo`` is required to read private repositories the
#: user already has access to; ``read:user`` powers the connection card.
GITHUB_SCOPES = ("read:user", "user:email", "repo")

STATE_TTL_SECONDS = 600
MAX_FILE_BYTES = 200_000
README_MAX_CHARS = 200_000
FILE_EXTENSIONS = (".md", ".markdown", ".txt", ".rst", ".adoc")

T = TypeVar("T")

MISSING_CONFIGURATION_HELP = [
    "Create a GitHub OAuth App: GitHub -> Settings -> Developer settings -> OAuth Apps -> New.",
    "Set the authorization callback URL to your backend callback, e.g. "
    "http://localhost:8000/api/v1/github/callback",
    "Copy the Client ID into GITHUB_CLIENT_ID and generate a client secret into "
    "GITHUB_CLIENT_SECRET.",
    "Generate a Fernet key (python -c \"from cryptography.fernet import Fernet;"
    "print(Fernet.generate_key().decode())\") and set GITHUB_TOKEN_ENCRYPTION_KEY.",
    "Set GITHUB_OAUTH_REDIRECT_URI and GITHUB_OAUTH_FRONTEND_REDIRECT to match your deployment.",
]


# ---------------------------------------------------------------------------
# Token encryption
# ---------------------------------------------------------------------------
class TokenCipher:
    """Fernet wrapper used to protect GitHub access tokens at rest."""

    def __init__(self, key: str | None) -> None:
        self._fernet: Fernet | None = None
        if key:
            try:
                self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
            except (ValueError, TypeError):
                logger.error("GITHUB_TOKEN_ENCRYPTION_KEY is not a valid Fernet key.")

    @property
    def configured(self) -> bool:
        return self._fernet is not None

    def encrypt(self, raw: str) -> str:
        if self._fernet is None:
            raise NotConfiguredError(
                "GitHub token encryption is not configured.",
                code="github_not_configured",
                details={"remediation": MISSING_CONFIGURATION_HELP},
            )
        return self._fernet.encrypt(raw.encode()).decode()

    def decrypt(self, token: str) -> str:
        if self._fernet is None:
            raise NotConfiguredError(
                "GitHub token encryption is not configured.",
                code="github_not_configured",
                details={"remediation": MISSING_CONFIGURATION_HELP},
            )
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise AuthError(
                "Stored GitHub token could not be decrypted; please reconnect GitHub.",
                code="github_token_unreadable",
            ) from exc


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------
class GitHubOAuth:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.github_client_id
            and self.settings.github_client_secret
            and self.settings.github_token_encryption_key
        )

    def ensure_configured(self) -> None:
        if not self.configured:
            raise NotConfiguredError(
                "GitHub OAuth is not configured on the server. This integration boundary is "
                "intentionally inert until credentials are supplied.",
                code="github_not_configured",
                details={"remediation": MISSING_CONFIGURATION_HELP},
            )

    # --- state ---------------------------------------------------------
    def create_state(self, user_id: uuid.UUID) -> str:
        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": str(user_id),
            "nonce": uuid.uuid4().hex,
            "purpose": "github_oauth",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=STATE_TTL_SECONDS)).timestamp()),
        }
        return jwt.encode(payload, self._state_secret(), algorithm="HS256")

    def verify_state(self, state: str) -> uuid.UUID:
        try:
            payload = jwt.decode(state, self._state_secret(), algorithms=["HS256"])
        except jwt.ExpiredSignatureError as exc:
            raise AuthError(
                "The GitHub authorisation request expired. Please start the connection again.",
                code="oauth_state_expired",
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise AuthError("Invalid GitHub authorisation state.", code="invalid_oauth_state") from exc

        if payload.get("purpose") != "github_oauth":
            raise AuthError("Invalid GitHub authorisation state.", code="invalid_oauth_state")
        try:
            return uuid.UUID(str(payload["sub"]))
        except (KeyError, ValueError) as exc:
            raise AuthError("Invalid GitHub authorisation state.", code="invalid_oauth_state") from exc

    def _state_secret(self) -> str:
        secret = self.settings.github_client_secret
        if not secret:
            raise NotConfiguredError(
                "GitHub OAuth is not configured on the server.",
                code="github_not_configured",
                details={"remediation": MISSING_CONFIGURATION_HELP},
            )
        return secret

    # --- urls ----------------------------------------------------------
    def build_authorize_url(self, state: str) -> str:
        self.ensure_configured()
        query = urlencode(
            {
                "client_id": self.settings.github_client_id,
                "redirect_uri": self.settings.github_oauth_redirect_uri,
                "scope": " ".join(GITHUB_SCOPES),
                "state": state,
                "allow_signup": "true",
            }
        )
        return f"{GITHUB_AUTHORIZE_URL}?{query}"

    # --- code exchange -------------------------------------------------
    def exchange_code(self, code: str) -> dict[str, Any]:
        self.ensure_configured()
        try:
            response = httpx.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": self.settings.github_client_id,
                    "client_secret": self.settings.github_client_secret,
                    "code": code,
                    "redirect_uri": self.settings.github_oauth_redirect_uri,
                },
                headers={"Accept": "application/json"},
                timeout=20.0,
            )
        except httpx.HTTPError as exc:
            raise UpstreamError(
                "Could not reach GitHub to exchange the authorisation code."
            ) from exc

        if response.status_code >= 400:
            raise UpstreamError(
                "GitHub rejected the authorisation code exchange.",
                details={"status_code": response.status_code},
            )
        payload = response.json()
        if payload.get("error"):
            raise AuthError(
                f"GitHub authorisation failed: {payload.get('error_description') or payload['error']}",
                code="github_oauth_failed",
            )
        if not payload.get("access_token"):
            raise AuthError("GitHub did not return an access token.", code="github_oauth_failed")
        return payload

    def fetch_authenticated_user(self, access_token: str) -> dict[str, Any]:
        try:
            response = httpx.get(
                GITHUB_API_USER_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=20.0,
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("Could not reach the GitHub API.") from exc

        if response.status_code == 401:
            raise AuthError(
                "GitHub rejected the access token. Please reconnect your GitHub account.",
                code="github_unauthorised",
            )
        if response.status_code >= 400:
            raise UpstreamError(
                "GitHub API returned an unexpected response for the user profile.",
                details={"status_code": response.status_code},
            )
        return response.json()


# ---------------------------------------------------------------------------
# REST client
# ---------------------------------------------------------------------------
class GitHubClient:
    """Thin error-translating wrapper around PyGithub."""

    def __init__(self, token: str, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.token = token
        try:
            self._gh = Github(auth=Auth.Token(token), timeout=20, per_page=100)
        except Exception as exc:  # pragma: no cover - defensive
            raise UpstreamError("Could not initialise the GitHub client.") from exc

    # --- helpers -------------------------------------------------------
    def _call(self, operation: str, fn: Callable[[], T]) -> T:
        try:
            return fn()
        except GithubException as exc:
            raise self._translate(exc, operation) from exc
        except httpx.HTTPError as exc:  # pragma: no cover - network layer
            raise UpstreamError(f"Network error while calling GitHub ({operation}).") from exc

    def _translate(self, exc: GithubException, operation: str) -> Exception:
        status = getattr(exc, "status", None)
        headers = getattr(exc, "headers", {}) or {}
        data = getattr(exc, "data", {}) or {}
        message = str(data.get("message") or getattr(exc, "data", "") or "")

        remaining = headers.get("x-ratelimit-remaining") or headers.get("X-RateLimit-Remaining")
        reset = headers.get("x-ratelimit-reset") or headers.get("X-RateLimit-Reset")

        if status == 401:
            return AuthError(
                "GitHub access was revoked or the token expired. Reconnect your GitHub account.",
                code="github_unauthorised",
            )
        if status == 403 and (remaining == "0" or "rate limit" in message.lower()):
            reset_at = None
            if reset:
                try:
                    reset_at = datetime.fromtimestamp(int(reset), tz=timezone.utc).isoformat()
                except (TypeError, ValueError):
                    reset_at = None
            return RateLimitError(
                "GitHub API rate limit reached. Please retry after the limit resets.",
                details={"operation": operation, "resets_at": reset_at},
            )
        if status == 404:
            return NotFoundError(
                "The repository, issue or pull request is not accessible with the connected "
                "GitHub account.",
                details={"operation": operation},
            )
        if status == 409:
            return UpstreamError(
                "The repository is empty; there is nothing to ingest yet.",
                details={"operation": operation},
            )
        if status == 451:
            return UpstreamError(
                "GitHub blocked access to this resource for legal reasons.",
                details={"operation": operation},
            )
        return UpstreamError(
            f"GitHub API error during '{operation}'.",
            details={"status_code": status, "github_message": message[:300]},
        )

    # --- repositories --------------------------------------------------
    def get_repository(self, full_name: str):
        return self._call("get_repository", lambda: self._gh.get_repo(full_name))

    def list_repositories(self, limit: int = 100) -> list[Any]:
        user = self._call("get_authenticated_user", self._gh.get_user)
        try:
            repos = user.get_repos(sort="updated", direction="desc")
        except GithubException as exc:
            raise self._translate(exc, "list_repositories") from exc
        collected: list[Any] = []
        try:
            for repo in repos:
                collected.append(repo)
                if len(collected) >= limit:
                    break
        except GithubException as exc:
            if not collected:
                raise self._translate(exc, "list_repositories") from exc
            logger.warning("Stopped listing repositories early: %s", exc.status)
        return collected

    # --- data ----------------------------------------------------------
    def list_commits(self, repo, limit: int) -> list[Any]:
        return self._paginate("list_commits", lambda: repo.get_commits(), limit)

    def list_issues(self, repo, limit: int) -> list[Any]:
        items = self._paginate("list_issues", lambda: repo.get_issues(state="all"), limit)
        # The GitHub issues endpoint also returns pull requests.
        return [item for item in items if item.pull_request is None][:limit]

    def list_pull_requests(self, repo, limit: int) -> list[Any]:
        return self._paginate("list_pull_requests", lambda: repo.get_pulls(state="all"), limit)

    def get_readme(self, repo):
        try:
            return repo.get_readme()
        except GithubException as exc:
            if getattr(exc, "status", None) == 404:
                return None
            raise self._translate(exc, "get_readme") from exc

    def list_root_files(self, repo) -> list[Any]:
        results: list[Any] = []
        for path in ("", "docs", "doc", "documentation"):
            try:
                contents = repo.get_contents(path)
            except GithubException as exc:
                if getattr(exc, "status", None) == 404:
                    continue
                raise self._translate(exc, "list_files") from exc
            if not isinstance(contents, list):
                contents = [contents]
            results.extend(contents)
        return results

    def commit_files(self, repo, sha: str) -> list[str]:
        try:
            commit = repo.get_commit(sha)
            return [item.filename for item in (commit.files or [])]
        except GithubException as exc:
            logger.warning("Could not fetch changed files for %s (%s)", sha, exc.status)
            return []

    def pull_request_files(self, repo, number: int) -> list[str]:
        try:
            pull = repo.get_pull(number)
            return [item.filename for item in pull.get_files()]
        except GithubException as exc:
            logger.warning("Could not fetch files for PR #%s (%s)", number, exc.status)
            return []

    def _paginate(self, operation: str, factory: Callable[[], Any], limit: int) -> list[Any]:
        try:
            paginated = factory()
        except GithubException as exc:
            raise self._translate(exc, operation) from exc

        collected: list[Any] = []
        try:
            for item in paginated:
                collected.append(item)
                if len(collected) >= limit:
                    break
        except GithubException as exc:
            if not collected:
                raise self._translate(exc, operation) from exc
            logger.warning("Stopped paging %s early: %s", operation, exc.status)
        return collected


# ---------------------------------------------------------------------------
# Service facade
# ---------------------------------------------------------------------------
@dataclass
class ImportOutcome:
    results: list[IngestionResult] = field(default_factory=list)

    @property
    def imported(self) -> int:
        return sum(1 for item in self.results if item.status.value == "completed")

    @property
    def duplicates(self) -> int:
        return sum(1 for item in self.results if item.status.value == "duplicate")

    @property
    def skipped(self) -> int:
        return sum(1 for item in self.results if item.status.value == "skipped")

    @property
    def failed(self) -> int:
        return sum(1 for item in self.results if item.status.value == "failed")


class GitHubService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.oauth = GitHubOAuth(self.settings)
        self.cipher = TokenCipher(self.settings.github_token_encryption_key)
        self.connections = GitHubRepository(db)
        self.projects = ProjectsRepository(db)

    # --- connection ----------------------------------------------------
    def status(self, user: User) -> GitHubStatusResponse:
        connection = self.connections.get_for_user(user.id)
        configured = bool(
            (self.oauth.configured and self.cipher.configured)
            or self.settings.github_token
            or connection is not None
        )
        if connection is None:
            if self.settings.github_token:
                try:
                    profile = self.oauth.fetch_authenticated_user(self.settings.github_token)
                    return GitHubStatusResponse(
                        configured=True,
                        connected=True,
                        login=profile.get("login"),
                        avatar_url=profile.get("avatar_url"),
                        github_user_id=str(profile.get("id")) if profile.get("id") is not None else None,
                        scopes=["repo", "read:user", "read:org", "user:email"],
                    )
                except Exception as exc:
                    logger.warning("Could not fetch user profile with github_token: %s", exc)
                    return GitHubStatusResponse(
                        configured=True,
                        connected=False,
                        message="GitHub token configured but user profile fetch failed.",
                    )
            return GitHubStatusResponse(
                configured=configured,
                connected=False,
                message=(
                    None
                    if configured
                    else "GitHub OAuth or GITHUB_TOKEN is not configured on the server. "
                    "Set the GITHUB_* environment variables to enable it."
                ),
            )
        return GitHubStatusResponse(
            configured=configured,
            connected=True,
            login=connection.github_login,
            avatar_url=connection.github_avatar_url,
            github_user_id=connection.github_user_id,
            scopes=(connection.scopes or "").split() if connection.scopes else list(GITHUB_SCOPES),
            connected_at=connection.connected_at,
        )

    def connect_token(self, user: User, token: str) -> GitHubStatusResponse:
        """Connect a GitHub Personal Access Token (PAT) directly."""
        profile = self.oauth.fetch_authenticated_user(token)
        # Use existing cipher or derive a Fernet key if encryption key is unconfigured
        cipher = self.cipher
        if not cipher.configured:
            cipher = TokenCipher(Fernet.generate_key().decode())
        encrypted = cipher.encrypt(token)
        self.connections.upsert(
            user_id=user.id,
            encrypted_access_token=encrypted,
            github_user_id=str(profile.get("id")) if profile.get("id") is not None else None,
            github_login=profile.get("login"),
            github_avatar_url=profile.get("avatar_url"),
            scopes="repo read:user read:org user:email",
            token_type="bearer",
        )
        self.db.commit()
        audit_service.record(
            self.db,
            action="github.connected",
            user_id=user.id,
            resource_type="github_connection",
            metadata={"login": profile.get("login"), "type": "pat"},
        )
        return self.status(user)

    def start_connect(self, user: User) -> tuple[str, str]:
        self.oauth.ensure_configured()
        state = self.oauth.create_state(user.id)
        return self.oauth.build_authorize_url(state), state

    def complete_connect(self, *, state: str, code: str) -> User:
        """Handle the OAuth callback and store an encrypted token."""
        self.oauth.ensure_configured()
        user_id = self.oauth.verify_state(state)

        from app.repositories.users import UsersRepository

        user = UsersRepository(self.db).get(user_id)
        if user is None:
            raise AuthError("The GitHub connection no longer matches a known user.")

        token_payload = self.oauth.exchange_code(code)
        access_token = token_payload["access_token"]
        scopes = token_payload.get("scope") or " ".join(GITHUB_SCOPES)
        profile = self.oauth.fetch_authenticated_user(access_token)

        self.connections.upsert(
            user_id=user.id,
            encrypted_access_token=self.cipher.encrypt(access_token),
            github_user_id=str(profile.get("id")) if profile.get("id") is not None else None,
            github_login=profile.get("login"),
            github_avatar_url=profile.get("avatar_url"),
            scopes=scopes,
            token_type=token_payload.get("token_type", "bearer"),
        )
        self.db.commit()

        audit_service.record(
            self.db,
            action="github.connected",
            user_id=user.id,
            resource_type="github_connection",
            metadata={"login": profile.get("login")},
        )
        return user

    def disconnect(self, user: User) -> bool:
        removed = self.connections.delete_for_user(user.id)
        self.db.commit()
        if removed:
            audit_service.record(
                self.db, action="github.disconnected", user_id=user.id, resource_type="github_connection"
            )
        return removed

    def _client_for(self, user: User) -> GitHubClient:
        connection = self.connections.get_for_user(user.id)
        if connection is not None:
            token = self.cipher.decrypt(connection.encrypted_access_token)
            return GitHubClient(token, self.settings)
        if self.settings.github_token:
            return GitHubClient(self.settings.github_token, self.settings)
        raise AuthError(
            "No GitHub account is connected. Connect GitHub before importing sources.",
            code="github_not_connected",
        )

    # --- repositories --------------------------------------------------
    def list_repositories(self, user: User, *, limit: int = 100) -> list[GitHubRepositorySummary]:
        client = self._client_for(user)
        repos = client.list_repositories(limit=limit)
        return [
            GitHubRepositorySummary(
                id=str(repo.id),
                full_name=repo.full_name,
                name=repo.name,
                owner=repo.owner.login if repo.owner else "",
                private=bool(repo.private),
                description=repo.description,
                default_branch=repo.default_branch,
                html_url=repo.html_url,
                language=repo.language,
                stars=int(repo.stargazers_count or 0),
                updated_at=repo.updated_at,
            )
            for repo in repos
        ]

    def get_repository_detail(self, user: User, full_name: str) -> dict[str, Any]:
        client = self._client_for(user)
        repo = client.get_repository(full_name)
        readme = client.get_readme(repo)
        branch = None
        try:
            branch = repo.get_branch(repo.default_branch).commit.sha
        except GithubException:  # pragma: no cover - defensive
            branch = None
        return {
            "repository": GitHubRepositorySummary(
                id=str(repo.id),
                full_name=repo.full_name,
                name=repo.name,
                owner=repo.owner.login if repo.owner else "",
                private=bool(repo.private),
                description=repo.description,
                default_branch=repo.default_branch,
                html_url=repo.html_url,
                language=repo.language,
                stars=int(repo.stargazers_count or 0),
                updated_at=repo.updated_at,
            ),
            "readme_present": readme is not None,
            "default_branch_sha": branch,
            "open_issues": int(repo.open_issues_count or 0),
        }

    # --- import --------------------------------------------------------
    def import_repository(
        self,
        project: Project,
        payload: GitHubImportRequest,
        *,
        user: User,
    ) -> GitHubImportResponse:
        client = self._client_for(user)
        repo = client.get_repository(payload.repository)

        access_label = AccessLabel.PRIVATE if repo.private else AccessLabel.PUBLIC
        link = self.projects.upsert_repository(
            project_id=project.id,
            full_name=repo.full_name,
            provider="github",
            external_id=str(repo.id),
            description=repo.description,
            default_branch=repo.default_branch,
            is_private=bool(repo.private),
            html_url=repo.html_url,
            meta={
                "language": repo.language,
                "stars": int(repo.stargazers_count or 0),
                "open_issues": int(repo.open_issues_count or 0),
            },
        )
        self.db.commit()
        self.db.refresh(link)

        ingestion = IngestionService(self.db)
        outcome = ImportOutcome()
        repo_meta = {
            "repository": repo.full_name,
            "repository_url": repo.html_url,
            "repository_private": bool(repo.private),
            "provider": "github",
        }

        if payload.include_commits:
            for commit in client.list_commits(repo, payload.max_items):
                outcome.results.append(self._ingest_commit(
                    ingestion, project, repo, commit, repo_meta, access_label,
                    payload.include_changed_files, client,
                ))

        if payload.include_issues:
            for issue in client.list_issues(repo, payload.max_items):
                outcome.results.append(
                    self._ingest_issue(ingestion, project, repo, issue, repo_meta, access_label)
                )

        if payload.include_pull_requests:
            for pull in client.list_pull_requests(repo, payload.max_items):
                outcome.results.append(self._ingest_pull_request(
                    ingestion, project, repo, pull, repo_meta, access_label,
                    payload.include_changed_files, client,
                ))

        if payload.include_readme:
            result = self._ingest_readme(ingestion, project, repo, client, repo_meta, access_label)
            if result is not None:
                outcome.results.append(result)

        if payload.include_files:
            for content_file in client.list_root_files(repo):
                result = self._ingest_file(
                    ingestion, project, repo, content_file, repo_meta, access_label
                )
                if result is not None:
                    outcome.results.append(result)
                if len(outcome.results) > payload.max_items * 5:
                    break

        audit_service.record(
            self.db,
            action="github.repository_imported",
            user_id=user.id,
            workspace_id=project.workspace_id,
            resource_type="project",
            resource_id=project.id,
            metadata={
                "repository": repo.full_name,
                "imported": outcome.imported,
                "duplicates": outcome.duplicates,
                "failed": outcome.failed,
            },
        )

        return GitHubImportResponse(
            repository=self._repository_schema(link),
            imported=outcome.imported,
            duplicates=outcome.duplicates,
            skipped=outcome.skipped,
            failed=outcome.failed,
            results=outcome.results,
        )

    # --- per-record ingest --------------------------------------------
    def _ingest_commit(
        self, ingestion, project, repo, commit, repo_meta, access_label, include_files, client
    ) -> IngestionResult:
        sha = commit.sha
        author = (commit.commit.author.name if commit.commit and commit.commit.author else None)
        committed_at = commit.commit.author.date if commit.commit and commit.commit.author else None
        message = (commit.commit.message if commit.commit else "") or ""
        changed: list[str] = []
        if include_files:
            changed = client.commit_files(repo, sha)

        body = [
            f"Repository: {repo.full_name}",
            f"Commit: {sha}",
            f"Author: {author or 'unknown'}",
            f"Date: {committed_at.isoformat() if committed_at else 'unknown'}",
            "",
            message.strip(),
        ]
        if changed:
            body.extend(["", "Changed files:", *[f"- {name}" for name in changed[:100]]])

        summary = message.strip().splitlines()[0][:200] if message.strip() else f"Commit {sha[:7]}"
        return ingestion.ingest_text_artifact(
            project,
            source_type=SourceType.GITHUB_COMMIT,
            source_name=summary,
            content="\n".join(body),
            external_id=sha,
            author=author,
            created_at_source=committed_at,
            metadata={
                **repo_meta,
                "commit_sha": sha,
                "commit_url": commit.html_url,
                "commit_message_length": len(message),
                "changed_files": changed,
                "changed_file_count": len(changed) or None,
                "has_changed_files": bool(changed),
            },
            access_label=access_label,
            source_url=commit.html_url,
        )

    def _ingest_issue(self, ingestion, project, repo, issue, repo_meta, access_label):
        labels = [label.name for label in (issue.labels or [])]
        body = [
            f"Repository: {repo.full_name}",
            f"Issue #{issue.number}: {issue.title}",
            f"Author: {issue.user.login if issue.user else 'unknown'}",
            f"State: {issue.state}",
            f"Labels: {', '.join(labels) or 'none'}",
            f"Created: {issue.created_at.isoformat() if issue.created_at else 'unknown'}",
            f"Updated: {issue.updated_at.isoformat() if issue.updated_at else 'unknown'}",
            "",
            (issue.body or "").strip() or "(no description)",
        ]
        return ingestion.ingest_text_artifact(
            project,
            source_type=SourceType.GITHUB_ISSUE,
            source_name=f"#{issue.number} {issue.title}"[:300],
            content="\n".join(body),
            external_id=f"issue#{issue.number}",
            author=issue.user.login if issue.user else None,
            created_at_source=issue.created_at,
            metadata={
                **repo_meta,
                "issue_number": issue.number,
                "state": issue.state,
                "labels": labels,
                "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
                "comments": int(issue.comments or 0),
            },
            access_label=access_label,
            source_url=issue.html_url,
        )

    def _ingest_pull_request(
        self, ingestion, project, repo, pull, repo_meta, access_label, include_files, client
    ):
        changed: list[str] = []
        if include_files:
            changed = client.pull_request_files(repo, pull.number)

        merged = bool(getattr(pull, "merged", False))
        body = [
            f"Repository: {repo.full_name}",
            f"Pull request #{pull.number}: {pull.title}",
            f"Author: {pull.user.login if pull.user else 'unknown'}",
            f"State: {pull.state}",
            f"Merged: {'yes' if merged else 'no'}",
            f"Created: {pull.created_at.isoformat() if pull.created_at else 'unknown'}",
            f"Updated: {pull.updated_at.isoformat() if pull.updated_at else 'unknown'}",
            f"Changed files: {pull.changed_files}",
            "",
            (pull.body or "").strip() or "(no description)",
        ]
        if changed:
            body.extend(["", "Files:", *[f"- {name}" for name in changed[:100]]])

        return ingestion.ingest_text_artifact(
            project,
            source_type=SourceType.GITHUB_PULL_REQUEST,
            source_name=f"PR #{pull.number} {pull.title}"[:300],
            content="\n".join(body),
            external_id=f"pr#{pull.number}",
            author=pull.user.login if pull.user else None,
            created_at_source=pull.created_at,
            metadata={
                **repo_meta,
                "pull_request_number": pull.number,
                "state": pull.state,
                "merged": merged,
                "merged_at": pull.merged_at.isoformat() if getattr(pull, "merged_at", None) else None,
                "changed_file_count": pull.changed_files,
                "changed_files": changed,
                "base_branch": pull.base.ref if pull.base else None,
                "head_branch": pull.head.ref if pull.head else None,
            },
            access_label=access_label,
            source_url=pull.html_url,
        )

    def _ingest_readme(self, ingestion, project, repo, client, repo_meta, access_label):
        readme = client.get_readme(repo)
        if readme is None:
            return None
        raw = readme.decoded_content or b""
        text = raw[:README_MAX_CHARS].decode("utf-8", errors="replace")
        return ingestion.ingest_text_artifact(
            project,
            source_type=SourceType.GITHUB_README,
            source_name=readme.path or "README",
            content=text,
            external_id="readme",
            author=None,
            created_at_source=None,
            metadata={
                **repo_meta,
                "readme_path": readme.path,
                "readme_size_bytes": len(raw),
                "truncated": len(raw) > README_MAX_CHARS,
            },
            access_label=access_label,
            source_url=readme.html_url if hasattr(readme, "html_url") else None,
            mime_type="text/markdown",
            size_bytes=len(raw),
        )

    def _ingest_file(self, ingestion, project, repo, content_file, repo_meta, access_label):
        path = getattr(content_file, "path", "") or ""
        if getattr(content_file, "type", None) != "file":
            return None
        lowered = path.lower()
        if not lowered.endswith(FILE_EXTENSIONS):
            return None
        if int(getattr(content_file, "size", 0) or 0) > MAX_FILE_BYTES:
            return IngestionResult(
                filename=path,
                status=ProcessingStatus.SKIPPED,
                message=f"File exceeds the {MAX_FILE_BYTES} byte limit for repository documents.",
            )
        try:
            raw = content_file.decoded_content or b""
        except Exception:  # pragma: no cover - binary/encoded files
            return None
        text = raw.decode("utf-8", errors="replace")
        return ingestion.ingest_text_artifact(
            project,
            source_type=SourceType.GITHUB_FILE,
            source_name=path,
            content=text,
            external_id=f"file:{path}",
            author=None,
            created_at_source=None,
            metadata={
                **repo_meta,
                "file_path": path,
                "file_size_bytes": len(raw),
            },
            access_label=access_label,
            mime_type="text/markdown" if lowered.endswith((".md", ".markdown")) else "text/plain",
            size_bytes=len(raw),
        )

    @staticmethod
    def _repository_schema(link):
        from app.schemas.project import RepositoryRead

        return RepositoryRead.model_validate(link)
