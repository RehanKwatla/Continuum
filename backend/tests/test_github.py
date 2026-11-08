"""GitHub integration boundary and error handling.

No GitHub credentials are present in CI/local test runs, so these tests assert
that the integration is a *clearly labelled boundary* — not fabricated data —
and that it fails with typed, actionable errors.
"""

from __future__ import annotations


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
