"""Workspace creation, listing, detail and tenant isolation."""

from __future__ import annotations


def test_create_workspace_makes_caller_owner(client, auth_headers) -> None:
    response = client.post("/api/v1/workspaces", json={"name": "Apollo"}, headers=auth_headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Apollo"
    assert body["role"] == "owner"
    assert body["project_count"] == 0
    assert len(body["members"]) == 1
    assert body["members"][0]["role"] == "owner"


def test_create_workspace_rejects_empty_name(client, auth_headers) -> None:
    response = client.post("/api/v1/workspaces", json={"name": ""}, headers=auth_headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_list_workspaces_returns_created(client, workspace, auth_headers) -> None:
    response = client.get("/api/v1/workspaces", headers=auth_headers)
    assert response.status_code == 200, response.text
    ids = [item["id"] for item in response.json()]
    assert workspace["id"] in ids


def test_get_workspace_detail(client, workspace, auth_headers) -> None:
    response = client.get(f"/api/v1/workspaces/{workspace['id']}", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == workspace["id"]


def test_foreign_workspace_is_reported_as_not_found(client, foreign_workspace, auth_headers) -> None:
    """Non-members must not be able to distinguish 'exists' from 'forbidden'."""
    response = client.get(f"/api/v1/workspaces/{foreign_workspace['id']}", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_unknown_workspace_id_is_not_found(client, auth_headers) -> None:
    import uuid

    response = client.get(f"/api/v1/workspaces/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404
