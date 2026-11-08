"""Project CRUD plus workspace isolation."""

from __future__ import annotations

import uuid

from app.models.project import Project


def test_create_project_inside_workspace(client, workspace, auth_headers) -> None:
    response = client.post(
        "/api/v1/projects",
        json={
            "workspace_id": workspace["id"],
            "name": "Payments Handover",
            "description": "Continuity plan for the billing service.",
            "departing_role": "Backend Engineer",
            "successor_role": "Platform Engineer",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["workspace_id"] == workspace["id"]
    assert body["status"] == "active"
    assert body["source_count"] == 0
    assert body["departing_role"] == "Backend Engineer"


def test_create_project_requires_target_workspace_membership(
    client, foreign_workspace, auth_headers
) -> None:
    response = client.post(
        "/api/v1/projects",
        json={"workspace_id": foreign_workspace["id"], "name": "Not Allowed"},
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_list_projects_paginates(client, project, auth_headers) -> None:
    response = client.get("/api/v1/projects", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["total"] >= 1
    assert any(item["id"] == project["id"] for item in body["items"])


def test_list_projects_filters_by_workspace(client, project, workspace, auth_headers) -> None:
    response = client.get(
        "/api/v1/projects", params={"workspace_id": workspace["id"]}, headers=auth_headers
    )
    assert response.status_code == 200
    assert all(item["workspace_id"] == workspace["id"] for item in response.json()["items"])


def test_list_projects_rejects_inaccessible_workspace(client, foreign_workspace, auth_headers):
    response = client.get(
        "/api/v1/projects", params={"workspace_id": foreign_workspace["id"]}, headers=auth_headers
    )
    assert response.status_code == 404


def test_get_project_detail(client, project, auth_headers) -> None:
    response = client.get(f"/api/v1/projects/{project['id']}", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == project["id"]
    assert body["workspace"]["id"] == project["workspace_id"]
    assert body["repositories"] == []


def test_patch_project_updates_fields(client, project, auth_headers) -> None:
    response = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"name": "Renamed Handover", "status": "handover_in_progress"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Renamed Handover"
    assert body["status"] == "handover_in_progress"


def test_delete_project_then_404(client, project, auth_headers) -> None:
    delete = client.delete(f"/api/v1/projects/{project['id']}", headers=auth_headers)
    assert delete.status_code == 204
    assert client.get(f"/api/v1/projects/{project['id']}", headers=auth_headers).status_code == 404


def test_project_in_foreign_workspace_is_hidden(
    client, db_session, foreign_workspace, auth_headers
) -> None:
    hidden = Project(workspace_id=uuid.UUID(foreign_workspace["id"]), name="Secret Project")
    db_session.add(hidden)
    db_session.commit()

    response = client.get(f"/api/v1/projects/{hidden.id}", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
