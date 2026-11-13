from __future__ import annotations

import httpx
import pytest

from app.services.public_github import (
    GitHubApiError,
    GitHubPublicConnector,
    RepositoryUrlError,
    parse_repository_url,
)
from app.services.repository_intelligence import file_skip_reason


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
    assert error.value.status == 302
    client.close()


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
