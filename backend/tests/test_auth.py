"""Authentication: identity always derives from a verified token.

Covers the error envelope for missing / malformed credentials, the
development-only bypass, and user provisioning.
"""

from __future__ import annotations


def test_protected_endpoint_requires_token(client) -> None:
    response = client.get("/api/v1/workspaces")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert "required" in body["error"]["message"].lower()


def test_non_bearer_scheme_is_rejected(client) -> None:
    response = client.get("/api/v1/workspaces", headers={"Authorization": "Basic abc123"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_unknown_token_without_supabase_config_is_service_unavailable(client) -> None:
    # Supabase is intentionally unconfigured in the test environment, so an
    # unrecognised token cannot be verified. The API says so explicitly rather
    # than silently authenticating.
    response = client.get("/api/v1/workspaces", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "auth_not_configured"


def test_dev_token_provisions_and_returns_profile(client, auth_headers) -> None:
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["auth_provider"] == "dev"
    assert body["is_dev_session"] is True
    user = body["user"]
    assert user["email"] == "dev.user@example.com"
    assert user["id"]


def test_session_sync_is_idempotent(client, auth_headers) -> None:
    first = client.post("/api/v1/auth/session", headers=auth_headers)
    second = client.post("/api/v1/auth/session", headers=auth_headers)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["user"]["id"] == second.json()["user"]["id"]


def test_client_supplied_user_id_is_ignored(client, auth_headers) -> None:
    """A spoofed user id header must not change the resolved identity."""
    headers = {**auth_headers, "X-User-Id": "00000000-0000-0000-0000-000000000000"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["user"]["id"] != "00000000-0000-0000-0000-000000000000"
