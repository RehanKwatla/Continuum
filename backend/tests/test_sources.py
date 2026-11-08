"""Source listing, filtering, retrieval, deletion and isolation."""

from __future__ import annotations

import uuid

from app.models.project import Project


def _upload(client, project_id, filename, payload, content_type, headers):
    return client.post(
        f"/api/v1/projects/{project_id}/sources/upload",
        files=[("files", (filename, payload, content_type))],
        headers=headers,
    )


def test_list_sources_is_empty_for_a_new_project(client, project, auth_headers) -> None:
    response = client.get(f"/api/v1/projects/{project['id']}/sources", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["meta"]["total"] == 0


def test_filter_sources_by_type(client, project, auth_headers, synthetic_pdf) -> None:
    _upload(client, project["id"], "doc.pdf", synthetic_pdf, "application/pdf", auth_headers)
    _upload(client, project["id"], "notes.md", b"# H\n\nbody\n", "text/markdown", auth_headers)

    only_pdf = client.get(
        f"/api/v1/projects/{project['id']}/sources",
        params={"source_type": "uploaded_pdf"},
        headers=auth_headers,
    ).json()
    assert only_pdf["meta"]["total"] == 1
    assert only_pdf["items"][0]["source_type"] == "uploaded_pdf"


def test_source_detail_returns_content(client, project, auth_headers) -> None:
    created = _upload(
        client, project["id"], "runbook.txt", b"Owned by platform.", "text/plain", auth_headers
    ).json()
    source_id = created["results"][0]["source_id"]

    response = client.get(f"/api/v1/sources/{source_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content"] == "Owned by platform."
    assert body["source_name"] == "runbook.txt"
    assert body["processing_status"] == "completed"


def test_unknown_source_is_not_found(client, auth_headers) -> None:
    response = client.get(f"/api/v1/sources/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_delete_source_removes_it(client, project, auth_headers) -> None:
    created = _upload(
        client, project["id"], "temp.txt", b"temporary knowledge", "text/plain", auth_headers
    ).json()
    source_id = created["results"][0]["source_id"]

    delete = client.delete(f"/api/v1/sources/{source_id}", headers=auth_headers)
    assert delete.status_code == 200, delete.text
    assert delete.json()["deleted"] is True
    assert client.get(f"/api/v1/sources/{source_id}", headers=auth_headers).status_code == 404
    listing = client.get(f"/api/v1/projects/{project['id']}/sources", headers=auth_headers).json()
    assert listing["meta"]["total"] == 0


def test_sources_of_foreign_project_are_hidden(
    client, db_session, foreign_workspace, auth_headers
) -> None:
    hidden = Project(workspace_id=uuid.UUID(foreign_workspace["id"]), name="Hidden")
    db_session.add(hidden)
    db_session.commit()

    listing = client.get(f"/api/v1/projects/{hidden.id}/sources", headers=auth_headers)
    assert listing.status_code == 404

    upload = _upload(client, hidden.id, "notes.txt", b"secret", "text/plain", auth_headers)
    assert upload.status_code == 404


def test_upload_to_unknown_project_is_not_found(client, auth_headers) -> None:
    response = _upload(client, uuid.uuid4(), "notes.txt", b"hello", "text/plain", auth_headers)
    assert response.status_code == 404
