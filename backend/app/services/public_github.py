"""Unauthenticated, allowlisted GitHub REST client for public repositories."""
from __future__ import annotations

import base64
import copy
import email.utils
import hashlib
import json
import re
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
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
    def __init__(
        self,
        status: int,
        message: str,
        *,
        code: str | None = None,
        retry_after_seconds: int | None = None,
        retry_at: int | None = None,
        request_id: str | None = None,
    ):
        self.status = status
        self.code = code or f"github_http_{status}"
        self.retry_after_seconds = retry_after_seconds
        self.retry_at = retry_at
        self.request_id = request_id
        super().__init__(message)


class _ResponseCache:
    """Small process-local TTL cache with single-flight request coalescing."""

    def __init__(self, max_entries: int = 512) -> None:
        self.max_entries = max_entries
        self.lock = threading.Lock()
        self.values: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self.inflight: dict[str, threading.Event] = {}

    def get_or_fetch(self, key: str, ttl: float, fetch):
        while True:
            with self.lock:
                now = time.monotonic()
                cached = self.values.get(key)
                if cached and cached[0] > now:
                    self.values.move_to_end(key)
                    return copy.deepcopy(cached[1])
                if cached:
                    self.values.pop(key, None)
                event = self.inflight.get(key)
                owner = event is None
                if owner:
                    event = threading.Event()
                    self.inflight[key] = event
            if not owner:
                if not event.wait(30):
                    raise GitHubApiError(503, "GitHub request is already in progress; retry shortly.", code="github_request_in_progress", retry_after_seconds=2)
                continue
            try:
                value = fetch()
                try:
                    cacheable = len(json.dumps(value, separators=(",", ":")).encode("utf-8")) <= 1_048_576
                except (TypeError, ValueError):
                    cacheable = False
                if ttl > 0 and cacheable:
                    with self.lock:
                        self.values[key] = (time.monotonic() + ttl, copy.deepcopy(value))
                        self.values.move_to_end(key)
                        while len(self.values) > self.max_entries:
                            self.values.popitem(last=False)
                return value
            finally:
                with self.lock:
                    self.inflight.pop(key, None)
                    event.set()


_RESPONSE_CACHE = _ResponseCache()
_RATE_LOCK = threading.Lock()
_RATE_LIMIT_UNTIL: dict[str, tuple[float, int | None]] = {}
_INVALID_TOKEN_UNTIL: dict[str, float] = {}


def _retry_after_seconds(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return max(0, int(float(value)))
    except (ValueError, OverflowError):
        try:
            date = email.utils.parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return max(0, int((date - datetime.now(timezone.utc)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return None


def _response_ttl(path: str) -> float:
    if re.fullmatch(r"/repos/[^/]+/[^/]+", path):
        return 300
    if path.endswith("/branches") or "/branches?" in path:
        return 120
    return 30


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
        self.settings = get_settings()
        self.api_base_url = self.settings.github_api_base_url.rstrip("/")
        self.token = self.settings.github_token.strip() if self.settings.github_token else None
        self.token_fingerprint = hashlib.sha256(self.token.encode()).hexdigest()[:20] if self.token else "anonymous"
        self.client = client or httpx.Client(
            base_url=self.api_base_url,
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
        cache_key = json.dumps((self.api_base_url, path, params or {}, self.token_fingerprint), sort_keys=True, separators=(",", ":"))
        return _RESPONSE_CACHE.get_or_fetch(cache_key, _response_ttl(path), lambda: self._request_json(path, params))

    def _request_json(self, path: str, params: dict | None):
        auth_key = self.token_fingerprint
        now = time.time()
        with _RATE_LOCK:
            cooldown = _RATE_LIMIT_UNTIL.get(auth_key)
            if cooldown and cooldown[0] > now:
                retry_seconds = max(1, int(cooldown[0] - now + 0.999))
                raise GitHubApiError(429, "GitHub is rate limiting Continuum. Retry after the indicated time.", code="github_rate_limited", retry_after_seconds=retry_seconds, retry_at=cooldown[1])
            if cooldown:
                _RATE_LIMIT_UNTIL.pop(auth_key, None)
            token_bad_until = _INVALID_TOKEN_UNTIL.get(auth_key, 0)
            token = None if token_bad_until > now else self.token
            if token_bad_until and token_bad_until <= now:
                _INVALID_TOKEN_UNTIL.pop(auth_key, None)
            if token is None:
                auth_key = "anonymous"

        auth_fallback_used = token is None and self.token is not None
        attempts = 0
        last_error: Exception | None = None
        while attempts < 3:
            with _RATE_LOCK:
                cooldown = _RATE_LIMIT_UNTIL.get(auth_key)
            if cooldown and cooldown[0] > time.time():
                retry_seconds = max(1, int(cooldown[0] - time.time() + 0.999))
                raise GitHubApiError(429, "GitHub is rate limiting Continuum. Retry after the indicated time.", code="github_rate_limited", retry_after_seconds=retry_seconds, retry_at=cooldown[1])
            if self.request_count >= self.settings.repository_max_api_requests:
                raise GitHubApiError(429, "This repository analysis reached its configured GitHub request budget.", code="github_request_budget_exceeded")
            attempts += 1
            self.request_count += 1
            headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "Continuum-Repository-Intelligence"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            try:
                response = self.client.get(path, params=params, headers=headers)
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempts < 3:
                    time.sleep(0.15 * attempts)
                    continue
                raise GitHubApiError(503, "GitHub did not respond before the request timed out.", code="github_timeout", retry_after_seconds=3) from exc
            except httpx.RequestError as exc:
                last_error = exc
                if attempts < 3:
                    time.sleep(0.15 * attempts)
                    continue
                raise GitHubApiError(503, "GitHub is temporarily unreachable.", code="github_unavailable", retry_after_seconds=3) from exc

            upstream_request_id = response.headers.get("X-GitHub-Request-Id")
            if response.status_code == 401 and token and not auth_fallback_used:
                with _RATE_LOCK:
                    _INVALID_TOKEN_UNTIL[auth_key] = time.time() + 300
                token, auth_key, auth_fallback_used = None, "anonymous", True
                continue
            if response.status_code == 403 or response.status_code == 429:
                remaining = response.headers.get("X-RateLimit-Remaining")
                reset_value = response.headers.get("X-RateLimit-Reset")
                try:
                    reset_at = int(reset_value) if reset_value else None
                except ValueError:
                    reset_at = None
                retry_seconds = _retry_after_seconds(response.headers.get("Retry-After"))
                is_primary_limited = remaining == "0"
                try:
                    upstream_message = response.json().get("message", "")
                except (ValueError, AttributeError):
                    upstream_message = ""
                lower_message = str(upstream_message).lower()
                is_secondary_limited = bool(retry_seconds is not None or "secondary rate limit" in lower_message or "abuse detection" in lower_message)
                if response.status_code == 429 or is_primary_limited or is_secondary_limited:
                    if retry_seconds is None and reset_at is not None:
                        retry_seconds = max(0, reset_at - int(time.time()))
                    if retry_seconds is None:
                        retry_seconds = 60
                    retry_seconds = max(1, retry_seconds)
                    retry_at = reset_at or int(time.time()) + retry_seconds
                    with _RATE_LOCK:
                        _RATE_LIMIT_UNTIL[auth_key] = (time.time() + retry_seconds, retry_at)
                    raise GitHubApiError(429, "GitHub API rate limit reached. Wait before retrying.", code="github_rate_limited", retry_after_seconds=retry_seconds, retry_at=retry_at, request_id=upstream_request_id)
                raise GitHubApiError(403, "GitHub denied access to this repository. It may be private or restricted.", code="github_access_denied", request_id=upstream_request_id)
            if response.status_code == 404:
                raise GitHubApiError(404, "Public repository not found, or it is private/inaccessible.", code="github_repository_unavailable", request_id=upstream_request_id)
            if response.status_code == 401:
                raise GitHubApiError(503, "GitHub authentication is unavailable; check the server-side GITHUB_TOKEN.", code="github_auth_unavailable", request_id=upstream_request_id)
            if 300 <= response.status_code < 400:
                raise GitHubApiError(503, "GitHub returned an unsupported redirect.", code="github_redirect_unsupported", request_id=upstream_request_id)
            if response.status_code >= 500:
                if attempts < 3:
                    time.sleep(0.15 * attempts)
                    continue
                raise GitHubApiError(503, "GitHub is temporarily unavailable.", code="github_unavailable", retry_after_seconds=3, request_id=upstream_request_id)
            if response.status_code >= 400:
                raise GitHubApiError(503, "GitHub rejected the repository request.", code="github_upstream_error", request_id=upstream_request_id)
            try:
                return response.json()
            except ValueError as exc:
                raise GitHubApiError(503, "GitHub returned an invalid API response.", code="github_invalid_response", request_id=upstream_request_id) from exc
        raise GitHubApiError(503, "GitHub request failed after bounded retries.", code="github_unavailable", retry_after_seconds=3) from last_error

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
