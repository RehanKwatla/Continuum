from __future__ import annotations

import httpx
import pytest
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from app.services.public_github import (
    GitHubApiError,
    GitHubPublicConnector,
    RepositoryUrlError,
    parse_repository_url,
)
import app.services.public_github as public_github
from app.services.repository_intelligence import file_skip_reason
from app.api.v1.repository_intelligence import _error
from app.core.errors import ForbiddenError, NotFoundError, RateLimitError, UpstreamError


@pytest.mark.parametrize(
    ("url", "owner", "name", "branch"),
    [
        ("https://github.com/pallets/flask", "pallets", "flask", None),
        ("https://github.com/org/service/tree/release/2026", "org", "service", "release/2026"),
        ("https://github.com/org/service.git/", "org", "service", None),
    ],
)
def test_parse_public_repository_urls(url, owner, name, branch):
    parsed = parse_repository_url(url)
    assert (parsed.owner, parsed.name, parsed.branch) == (owner, name, branch)
    assert parsed.canonical_url == f"https://github.com/{owner}/{name}"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/org/repo",
        "https://github.com.evil.example/org/repo",
        "https://example.com/org/repo",
        "https://github.com/org",
        "https://github.com/org//repo",
        "https://github.com/org/repo/pull/42",
        "https://user:pass@github.com/org/repo",
        "https://github.com/org/repo?redirect=https://evil.example",
    ],
)
def test_reject_invalid_repository_urls(url):
    with pytest.raises(RepositoryUrlError):
        parse_repository_url(url)


def test_github_client_uses_allowlisted_host_and_maps_not_found():
    seen = []

    def handler(request):
        seen.append(request.url)
        return httpx.Response(404, json={"message": "Not Found"})

    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    connector = GitHubPublicConnector(client=client)
    with pytest.raises(GitHubApiError) as error:
        connector.repository("pallets", "flask")
    assert error.value.status == 404
    assert seen[0].host == "api.github.com"
    assert seen[0].path == "/repos/pallets/flask"
    client.close()


def test_github_client_does_not_follow_redirects():
    client = httpx.Client(
        base_url="https://api.github.com",
        follow_redirects=False,
        transport=httpx.MockTransport(lambda request: httpx.Response(302, headers={"Location": "https://evil.example"})),
    )
    connector = GitHubPublicConnector(client=client)
    with pytest.raises(GitHubApiError) as error:
        connector.repository("org", "repo")
    assert error.value.status == 503
    assert error.value.code == "github_redirect_unsupported"
    client.close()


def connector_for(handler, monkeypatch, token="test-server-token"):
    monkeypatch.setattr(public_github, "get_settings", lambda: SimpleNamespace(
        github_api_base_url="https://api.github.com", github_token=token,
        repository_max_api_requests=250,
    ))
    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    connector = GitHubPublicConnector(client=client)
    return connector, client


def test_server_token_used_and_invalid_token_falls_back(monkeypatch):
    auth_headers = []
    def handler(request):
        auth_headers.append(request.headers.get("Authorization"))
        if len(auth_headers) == 1:
            return httpx.Response(401, json={"message": "Bad credentials"})
        return httpx.Response(200, json={"full_name": "org/repo"})
    connector, client = connector_for(handler, monkeypatch)
    assert connector.get("/repos/org/repo")["full_name"] == "org/repo"
    assert auth_headers == ["Bearer test-server-token", None]
    client.close()


def test_primary_rate_limit_includes_reset_and_request_id(monkeypatch):
    reset = int(time.time()) + 120
    connector, client = connector_for(lambda request: httpx.Response(
        403, json={"message": "API rate limit exceeded"},
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset), "X-GitHub-Request-Id": "abc123"},
    ), monkeypatch, token="unique-rate-token")
    with pytest.raises(GitHubApiError) as error:
        connector.get("/repos/rate-test/repo")
    assert error.value.status == 429
    assert error.value.code == "github_rate_limited"
    assert error.value.retry_at == reset
    assert error.value.retry_after_seconds > 0
    assert error.value.request_id == "abc123"
    client.close()


def test_secondary_rate_limit_respects_retry_after(monkeypatch):
    connector, client = connector_for(lambda request: httpx.Response(
        403, json={"message": "You have exceeded a secondary rate limit"},
        headers={"Retry-After": "17"},
    ), monkeypatch, token="unique-secondary-token")
    with pytest.raises(GitHubApiError) as error:
        connector.get("/repos/secondary-test/repo")
    assert error.value.status == 429
    assert error.value.retry_after_seconds == 17
    client.close()


def test_non_rate_limit_forbidden_is_not_reported_as_rate_limit(monkeypatch):
    connector, client = connector_for(lambda request: httpx.Response(403, json={"message": "Resource not accessible"}), monkeypatch)
    with pytest.raises(GitHubApiError) as error:
        connector.get("/repos/forbidden-test/repo")
    assert error.value.status == 403
    assert error.value.code == "github_access_denied"
    client.close()


def test_metadata_is_cached_and_duplicate_concurrent_requests_are_coalesced(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        time.sleep(0.05)
        return httpx.Response(200, json={"full_name": "org/repo"})
    connector, client = connector_for(handler, monkeypatch)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: connector.get("/repos/cache-test/repo"), range(6)))
    assert all(result["full_name"] == "org/repo" for result in results)
    assert len(calls) == 1
    client.close()


def test_upstream_server_error_retries_are_bounded(monkeypatch):
    calls = []
    connector, client = connector_for(lambda request: (calls.append(1) or httpx.Response(502)), monkeypatch, token="unique-upstream-token")
    with pytest.raises(GitHubApiError) as error:
        connector.get("/repos/upstream-test/repo")
    assert error.value.status == 503
    assert len(calls) == 3
    client.close()


def test_upstream_timeout_maps_to_retryable_service_unavailable(monkeypatch):
    calls = []
    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("simulated timeout", request=request)
    connector, client = connector_for(handler, monkeypatch, token="unique-timeout-token")
    with pytest.raises(GitHubApiError) as error:
        connector.get("/repos/timeout-test/repo")
    assert error.value.status == 503
    assert error.value.code == "github_timeout"
    assert error.value.retry_after_seconds == 3
    assert len(calls) == 3
    client.close()


def test_rate_limit_cooldown_blocks_requests_then_allows_retry_after_reset(monkeypatch):
    calls = []
    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "90"}, json={"message": "Too many requests"})
        return httpx.Response(200, json={"full_name": "org/repo"})
    connector, client = connector_for(handler, monkeypatch, token="unique-reset-token")
    with pytest.raises(GitHubApiError) as first:
        connector.get("/repos/reset-test/repo")
    assert first.value.retry_after_seconds == 90
    with pytest.raises(GitHubApiError) as cooling_down:
        connector.get("/repos/reset-test/repo")
    assert cooling_down.value.status == 429
    assert len(calls) == 1
    with public_github._RATE_LOCK:
        public_github._RATE_LIMIT_UNTIL[connector.token_fingerprint] = (time.time() - 1, int(time.time()) - 1)
    assert connector.get("/repos/reset-test/repo")["full_name"] == "org/repo"
    assert len(calls) == 2
    client.close()


@pytest.mark.parametrize(
    ("status", "expected"),
    [(404, NotFoundError), (403, ForbiddenError), (429, RateLimitError), (503, UpstreamError)],
)
def test_repository_github_errors_map_to_meaningful_app_errors(status, expected):
    with pytest.raises(expected) as error:
        _error(GitHubApiError(status, "safe upstream message", retry_after_seconds=12, retry_at=1_800_000_000))
    if status == 429:
        assert error.value.status_code == 429
        assert error.value.details["retry_after_seconds"] == 12
        assert error.value.details["retry_at"] == 1_800_000_000
    if status == 503:
        assert error.value.status_code == 503


def test_branch_and_commit_listing_are_bounded_and_paginated():
    calls = []

    def handler(request):
        calls.append(request.url.params.get("page"))
        page = int(request.url.params["page"])
        if page == 1:
            return httpx.Response(200, json=[{"name": f"branch-{i}"} for i in range(100)])
        return httpx.Response(200, json=[{"name": "release/2026"}])

    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    connector = GitHubPublicConnector(client=client)
    branches = connector.branches("org", "repo")
    assert len(branches) == 101
    assert branches[-1]["name"] == "release/2026"
    assert calls == ["1", "2"]
    client.close()


def test_file_filter_keeps_supported_docs_and_excludes_secrets_and_generated_content():
    assert file_skip_reason("src/app.py", 120, 0, 1000) is None
    assert file_skip_reason("README.md", 120, 0, 1000) is None
    assert "safety filter" in file_skip_reason("config/.env.production", 80, 0, 1000)
    assert "safety filter" in file_skip_reason("keys/server.pem", 80, 0, 1000)
    assert "safety filter" in file_skip_reason("dist/app.min.js", 80, 0, 1000)
    assert "lockfile" in file_skip_reason("package-lock.json", 80, 0, 1000)


def test_file_filter_reports_size_budget_and_count_limits():
    assert "per-file" in file_skip_reason("src/app.ts", 300_000, 0, 1_000_000)
    assert "budget" in file_skip_reason("src/app.ts", 120, 0, 100)
    assert "file content limit" in file_skip_reason("src/app.ts", 120, 80, 1000)
