"""Integration: dashboard aggregates and end-to-end ingestion flow.

This is the Phase 1 + Phase 2 happy path: workspace -> project -> upload PDF
-> verify extracted content is stored -> dashboard reflects real numbers.
"""

from __future__ import annotations


def _upload(client, project_id, filename, payload, content_type, headers):
    return client.post(
        f"/api/v1/projects/{project_id}/sources/upload",
        files=[("files", (filename, payload, content_type))],
        headers=headers,
    )


def test_end_to_end_workspace_project_upload(client, auth_headers, synthetic_pdf) -> None:
    # 1. Workspace
    workspace = client.post(
        "/api/v1/workspaces", json={"name": "End to End"}, headers=auth_headers
    ).json()

    # 2. Project
    project = client.post(
        "/api/v1/projects",
        json={"workspace_id": workspace["id"], "name": "Billing Handover"},
        headers=auth_headers,
    ).json()

    # 3. Upload a PDF and a Markdown document
    pdf = _upload(client, project["id"], "handover.pdf", synthetic_pdf, "application/pdf", auth_headers).json()
    md = _upload(
        client,
        project["id"],
        "notes.md",
        b"# Deploy\n\nRun `make ship`.\n",
        "text/markdown",
        auth_headers,
    ).json()
    assert pdf["accepted"] == 1
    assert md["accepted"] == 1

    # 4. Extracted content is retrievable
    raw = client.get(f"/api/v1/sources/{pdf['results'][0]['source_id']}", headers=auth_headers).json()
    assert "rotate the signing key" in (raw["content"] or "").lower()

    # 5. Project detail shows real source counts
    detail = client.get(f"/api/v1/projects/{project['id']}", headers=auth_headers).json()
    assert detail["source_count"] == 2
    assert detail["source_type_counts"]["uploaded_pdf"] == 1
    assert detail["source_type_counts"]["uploaded_markdown"] == 1


def test_dashboard_reflects_persisted_data(client, project, auth_headers, synthetic_pdf) -> None:
    _upload(client, project["id"], "handover.pdf", synthetic_pdf, "application/pdf", auth_headers)

    response = client.get("/api/v1/dashboard", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["total_projects"] >= 1
    assert body["total_workspaces"] >= 1
    assert body["total_sources"] >= 1
    assert body["source_type_counts"]["uploaded_pdf"] == 1
    assert body["processing_status_counts"]["completed"] == 1
    assert any(item["id"] == project["id"] for item in body["recent_projects"])
    assert any(item["source_name"] == "handover.pdf" for item in body["recent_sources"])
    # Phase 3 items are explicitly flagged as upcoming, not shipped.
    assert "Claim extraction (Phase 3)" in body["upcoming"]
