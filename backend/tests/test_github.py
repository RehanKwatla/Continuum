"""GitHub integration boundary and error handling.

No GitHub credentials are present in CI/local test runs, so these tests assert
that the integration is a *clearly labelled boundary* — not fabricated data —
and that it fails with typed, actionable errors.
"""

from __future__ import annotations

import pytest
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _unconfigured_github_by_default(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "github_token", None)
    monkeypatch.setattr(settings, "github_client_id", None)
    monkeypatch.setattr(settings, "github_client_secret", None)
    monkeypatch.setattr(settings, "github_token_encryption_key", None)


def test_status_reports_not_configured(client, auth_headers) -> None:
    response = client.get("/api/v1/github/status", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is False
    assert body["connected"] is False
    assert body["message"]


def test_boundary_lists_remediation_steps(client) -> None:
    response = client.get("/api/v1/github/boundary")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is False
    assert body["remediation"], "the boundary must explain how to configure GitHub"
    assert any("GITHUB_CLIENT_ID" in step for step in body["remediation"])


def test_connect_without_configuration_returns_503(client, auth_headers) -> None:
    response = client.post("/api/v1/github/connect", headers=auth_headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "github_not_configured"


def test_list_repositories_requires_a_connection(client, auth_headers) -> None:
    response = client.get("/api/v1/github/repositories", headers=auth_headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "github_not_connected"


def test_import_requires_a_connection(client, project, auth_headers) -> None:
    response = client.post(
        f"/api/v1/projects/{project['id']}/github/import",
        json={"repository": "octocat/Hello-World"},
        headers=auth_headers,
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "github_not_connected"


def test_callback_without_parameters_redirects_to_frontend(client) -> None:
    response = client.get("/api/v1/github/callback", follow_redirects=False)
    assert response.status_code in (302, 307)
    location = response.headers["location"]
    assert "github=error" in location
    assert "missing_parameters" in location


def test_callback_with_error_redirects_with_reason(client) -> None:
    response = client.get(
        "/api/v1/github/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "github=error" in response.headers["location"]
    assert "access_denied" in response.headers["location"]


def test_callback_with_valid_state_but_no_connection_redirects_error(client) -> None:
    # A structurally valid but unverifiable callback must not 500.
    response = client.get(
        "/api/v1/github/callback",
        params={"code": "abc", "state": "not-a-real-state"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "github=error" in response.headers["location"]


def test_status_with_configured_github_token(client, auth_headers, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "github_token", "ghp_fake_token_for_test_1234567890")

    # Mock fetch_authenticated_user to avoid hitting real network in this test
    from app.services.github_service import GitHubOAuth

    monkeypatch.setattr(
        GitHubOAuth,
        "fetch_authenticated_user",
        lambda self, token: {"login": "testuser", "id": 12345, "avatar_url": "https://example.com/avatar.png"},
    )

    response = client.get("/api/v1/github/status", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is True
    assert body["connected"] is True
    assert body["login"] == "testuser"


def test_connect_token_endpoint(client, auth_headers, monkeypatch) -> None:
    from app.services.github_service import GitHubOAuth

    monkeypatch.setattr(
        GitHubOAuth,
        "fetch_authenticated_user",
        lambda self, token: {"login": "customuser", "id": 99999, "avatar_url": "https://example.com/u.png"},
    )

    response = client.post(
        "/api/v1/github/token",
        json={"token": "ghp_my_custom_token_1234567890"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is True
    assert body["connected"] is True
    assert body["login"] == "customuser"
