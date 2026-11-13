"""Unauthenticated, allowlisted GitHub REST client for public repositories."""
from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, unquote, urlsplit

import httpx

from app.core.config import get_settings

API = "https://api.github.com"
_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def _valid_segment(value: str) -> bool:
    return value not in {".", ".."} and bool(_SEGMENT.fullmatch(value))


class RepositoryUrlError(ValueError):
    pass


class GitHubApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


@dataclass(frozen=True)
class ParsedRepositoryUrl:
    owner: str
    name: str
    branch: str | None = None

    @property
    def canonical_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"


def parse_repository_url(value: str) -> ParsedRepositoryUrl:
    """Accept only canonical github.com repository URLs (optionally /tree/branch)."""
    try:
        parsed = urlsplit(value.strip())
    except ValueError as exc:
        raise RepositoryUrlError("Enter a valid GitHub repository URL.") from exc
    try:
        hostname, port = parsed.hostname, parsed.port
    except ValueError as exc:
        raise RepositoryUrlError("The repository URL has an invalid host or port.") from exc
    if parsed.scheme != "https" or hostname != "github.com" or port:
        raise RepositoryUrlError("Only https://github.com/ public repository URLs are supported.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RepositoryUrlError("The repository URL cannot include credentials, query, or fragment data.")
    raw_parts = parsed.path[1:].split("/") if parsed.path.startswith("/") else parsed.path.split("/")
    if raw_parts and raw_parts[-1] == "":
        raw_parts.pop()  # one trailing slash is accepted
    if any(not part for part in raw_parts):
        raise RepositoryUrlError("The repository URL contains an empty path segment.")
    parts = [unquote(part) for part in raw_parts]
    if len(parts) < 2 or not all(_valid_segment(part) for part in parts[:2]):
        raise RepositoryUrlError("Enter a repository URL in the form https://github.com/owner/repository.")
    owner, name = parts[:2]
    if name.endswith(".git"):
        name = name[:-4]
    if not name or name in {"tree", "pull", "issues", "settings", "actions", "projects"}:
        raise RepositoryUrlError("That URL does not identify a GitHub repository.")
    branch = None
    if len(parts) > 2:
        if len(parts) < 4 or parts[2] != "tree":
            raise RepositoryUrlError("Only repository URLs and /tree/{branch} URLs are supported.")
        branch = "/".join(parts[3:])
        if not branch or len(branch) > 200:
            raise RepositoryUrlError("The branch name is invalid.")
    return ParsedRepositoryUrl(owner=owner, name=name, branch=branch)


class GitProvider(Protocol):
    """Provider-neutral contract for repository discovery and records."""
    def validate_repository(self, value: str):
        raise NotImplementedError

    def get(self, path: str, params: dict | None = None):
        raise NotImplementedError

    def get_repository(self, owner: str, name: str):
        raise NotImplementedError

    def list_branches(self, owner: str, name: str):
        raise NotImplementedError

    def get_default_branch(self, owner: str, name: str):
        raise NotImplementedError

    def get_repository_tree(self, owner: str, name: str, sha: str):
        raise NotImplementedError

    def get_file_content(self, owner: str, name: str, sha: str, max_bytes: int):
        raise NotImplementedError

    def list_commits(self, owner: str, name: str, branch: str, limit: int = 50):
        raise NotImplementedError

    def get_commit_details(self, owner: str, name: str, sha: str):
        raise NotImplementedError

    def list_pull_requests(self, owner: str, name: str, limit: int = 100):
        raise NotImplementedError

    def list_issues(self, owner: str, name: str, limit: int = 100):
        raise NotImplementedError

    def get_languages(self, owner: str, name: str):
        raise NotImplementedError

    def list_directory(self, owner: str, name: str, path: str, ref: str):
        raise NotImplementedError

    def list_pull_request_files(self, owner: str, name: str, number: int):
        raise NotImplementedError

    def list_pull_request_reviews(self, owner: str, name: str, number: int):
        raise NotImplementedError


class GitHubPublicConnector(GitProvider):
    """REST v3 client that never sends user input as a host or redirect target."""
    def __init__(self, *, timeout: float = 12.0, client: httpx.Client | None = None):
        self.client = client or httpx.Client(
            base_url=API,
            timeout=httpx.Timeout(timeout, connect=5.0),
            follow_redirects=False,
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "Continuum-Repository-Intelligence"},
        )
        self._owns_client = client is None
        self.request_count = 0

    def close(self):
        if self._owns_client:
            self.client.close()

    def get(self, path: str, params: dict | None = None):
        if not path.startswith("/") or path.startswith("//") or ".." in path:
            raise ValueError("Unsafe GitHub API path")
        response = None
        for attempt in range(3):
            if self.request_count >= get_settings().repository_max_api_requests:
                raise GitHubApiError(429, "Repository analysis reached its API request limit.")
            self.request_count += 1
            try:
                response = self.client.get(path, params=params)
            except httpx.TimeoutException as exc:
                if attempt == 2:
                    raise GitHubApiError(504, "GitHub request timed out after bounded retries.") from exc
                time.sleep(0.2 * (2**attempt))
                continue
            except httpx.RequestError as exc:
                if attempt == 2:
                    raise GitHubApiError(503, "GitHub could not be reached after bounded retries.") from exc
                time.sleep(0.2 * (2**attempt))
                continue
            if response.status_code >= 500 and attempt < 2:
                time.sleep(0.2 * (2**attempt))
                continue
            break
        if 300 <= response.status_code < 400:
            raise GitHubApiError(response.status_code, "GitHub returned an unsupported redirect.")
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            reset = response.headers.get("X-RateLimit-Reset")
            suffix = f" Retry after Unix time {reset}." if reset else ""
            raise GitHubApiError(429, f"GitHub API rate limit reached.{suffix}")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            suffix = f" Retry after {retry_after} seconds." if retry_after else ""
            raise GitHubApiError(429, f"GitHub asked Continuum to slow down.{suffix}")
        if response.status_code >= 400:
            message = "GitHub could not access that public repository."
            if response.status_code == 404:
                message = "Public repository not found."
            elif response.status_code in (403, 429):
                message = "GitHub rate limit or access restriction encountered."
            raise GitHubApiError(response.status_code, message)
        try:
            return response.json()
        except ValueError as exc:
            raise GitHubApiError(502, "GitHub returned an unreadable API response.") from exc

    @staticmethod
    def _repo(owner: str, name: str) -> str:
        if not _valid_segment(owner) or not _valid_segment(name):
            raise RepositoryUrlError("Invalid GitHub owner or repository name.")
        return f"/repos/{owner}/{name}"

    def repository(self, owner: str, name: str):
        return self.get(self._repo(owner, name))

    def validate_repository(self, value: str):
        return validate_repository_url(value, self)

    def get_repository(self, owner: str, name: str):
        return self.repository(owner, name)

    def branches(self, owner: str, name: str):
        path, result = self._repo(owner, name) + "/branches", []
        for page in range(1, 6):
            batch = self.get(path, {"per_page": 100, "page": page})
            result.extend(batch)
            if len(batch) < 100:
                break
        return result

    def list_branches(self, owner: str, name: str):
        return self.branches(owner, name)

    def get_default_branch(self, owner: str, name: str):
        return self.repository(owner, name).get("default_branch")

    def languages(self, owner: str, name: str):
        return self.get(self._repo(owner, name) + "/languages")

    def get_languages(self, owner: str, name: str):
        return self.languages(owner, name)

    def tree(self, owner: str, name: str, sha: str):
        return self.get(self._repo(owner, name) + f"/git/trees/{sha}", {"recursive": "1"})

    def get_repository_tree(self, owner: str, name: str, sha: str):
        return self.tree(owner, name, sha)

    def commits(self, owner: str, name: str, branch: str, limit: int = 50):
        result, path = [], self._repo(owner, name) + "/commits"
        for page in range(1, (limit + 99) // 100 + 1):
            batch = self.get(path, {"sha": branch, "per_page": min(100, limit), "page": page})
            result.extend(batch[: max(0, limit - len(result))])
            if len(batch) < min(100, limit) or len(result) >= limit:
                break
        return result

    def list_commits(self, owner: str, name: str, branch: str, limit: int = 50):
        return self.commits(owner, name, branch, limit)

    def commit_details(self, owner: str, name: str, sha: str):
        return self.get(self._repo(owner, name) + f"/commits/{sha}")

    def get_commit_details(self, owner: str, name: str, sha: str):
        return self.commit_details(owner, name, sha)

    def records(self, owner: str, name: str, kind: str, limit: int = 100):
        result, path = [], self._repo(owner, name) + f"/{kind}"
        for page in range(1, (limit + 99) // 100 + 1):
            batch = self.get(path, {"state": "all", "per_page": min(100, limit), "page": page})
            result.extend(batch[: max(0, limit - len(result))])
            if len(batch) < min(100, limit) or len(result) >= limit:
                break
        return result

    def list_pull_requests(self, owner: str, name: str, limit: int = 100):
        return self.records(owner, name, "pulls", limit)

    def list_issues(self, owner: str, name: str, limit: int = 100):
        return self.records(owner, name, "issues", limit)

    def pull_files(self, owner: str, name: str, number: int):
        result, path = [], self._repo(owner, name) + f"/pulls/{number}/files"
        for page in range(1, 4):
            batch = self.get(path, {"per_page": 100, "page": page})
            result.extend(batch)
            if len(batch) < 100:
                break
        return result

    def list_pull_request_files(self, owner: str, name: str, number: int):
        return self.pull_files(owner, name, number)

    def pull_reviews(self, owner: str, name: str, number: int):
        result, path = [], self._repo(owner, name) + f"/pulls/{number}/reviews"
        for page in range(1, 3):
            batch = self.get(path, {"per_page": 100, "page": page})
            result.extend(batch)
            if len(batch) < 100:
                break
        return result

    def list_pull_request_reviews(self, owner: str, name: str, number: int):
        return self.pull_reviews(owner, name, number)

    def list_directory(self, owner: str, name: str, path: str, ref: str):
        return self.get(f"/repos/{owner}/{name}/contents/{quote(path, safe='/')}", {"ref": ref})

    def blob_text(self, owner: str, name: str, sha: str, max_bytes: int):
        blob = self.get(self._repo(owner, name) + f"/git/blobs/{sha}")
        if blob.get("encoding") != "base64":
            raise ValueError("GitHub returned an unsupported blob encoding")
        encoded = blob.get("content", "")
        if len(encoded) > max_bytes * 2:
            raise OverflowError("File exceeds the per-file content limit")
        raw = base64.b64decode(encoded, validate=False)
        if len(raw) > max_bytes:
            raise OverflowError("File exceeds the per-file content limit")
        return raw.decode("utf-8")

    def get_file_content(self, owner: str, name: str, sha: str, max_bytes: int):
        return self.blob_text(owner, name, sha, max_bytes)
