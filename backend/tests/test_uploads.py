"""File ingestion: PDF / Markdown / TXT uploads, validation and de-duplication."""

from __future__ import annotations


def _upload(client, project_id, filename, payload, content_type, headers):
    return client.post(
        f"/api/v1/projects/{project_id}/sources/upload",
        files=[("files", (filename, payload, content_type))],
        headers=headers,
    )


def test_upload_pdf_is_parsed_and_persisted(client, project, auth_headers, synthetic_pdf) -> None:
    response = _upload(client, project["id"], "handover.pdf", synthetic_pdf, "application/pdf", auth_headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["accepted"] == 1
    assert body["failed"] == 0
    result = body["results"][0]
    assert result["status"] == "completed"
    assert result["source_type"] == "uploaded_pdf"
    source_id = result["source_id"]

    detail = client.get(f"/api/v1/sources/{source_id}", headers=auth_headers)
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert "billing service" in (payload["content"] or "")
    assert payload["metadata"]["page_count"] == 2
    assert payload["content_hash"]


def test_upload_markdown_captures_headings(client, project, auth_headers) -> None:
    markdown = (
        "# Architecture\n\n"
        "The invoice service owns billing.\n\n"
        "## Deploy\n\n"
        "Deploy with `make ship`.\n\n"
        "See [runbook](https://example.com/runbook).\n"
    )
    response = _upload(
        client, project["id"], "notes.md", markdown.encode(), "text/markdown", auth_headers
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["accepted"] == 1
    source_id = body["results"][0]["source_id"]

    detail = client.get(f"/api/v1/sources/{source_id}", headers=auth_headers).json()
    assert detail["source_type"] == "uploaded_markdown"
    meta = detail["metadata"]
    assert meta["heading_count"] >= 2
    assert {h["text"] for h in meta["headings"]} >= {"Architecture", "Deploy"}
    assert meta["link_count"] == 1


def test_upload_text_captures_line_numbers(client, project, auth_headers) -> None:
    content = "Rotate the signing key every 90 days.\nOwned by the platform team.\n"
    response = _upload(
        client, project["id"], "runbook.txt", content.encode(), "text/plain", auth_headers
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["accepted"] == 1
    detail = client.get(f"/api/v1/sources/{body['results'][0]['source_id']}", headers=auth_headers).json()
    assert detail["source_type"] == "uploaded_text"
    assert detail["metadata"]["line_count"] >= 2
    assert "signing key" in detail["content"]


def test_unsupported_extension_is_rejected(client, project, auth_headers) -> None:
    response = _upload(
        client, project["id"], "malware.exe", b"MZ\x90\x00fake", "application/octet-stream", auth_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["accepted"] == 0
    assert body["failed"] == 1
    assert body["results"][0]["status"] == "failed"
    assert "Unsupported file type" in body["results"][0]["message"]


def test_deny_listed_filename_is_refused(client, project, auth_headers) -> None:
    response = _upload(
        client, project["id"], "id_rsa", b"-----BEGIN OPENSSH PRIVATE KEY-----\n", "text/plain", auth_headers
    )
    body = response.json()
    assert body["failed"] == 1
    assert "deny list" in body["results"][0]["message"].lower()


def test_declared_extension_must_match_content(client, project, auth_headers) -> None:
    # A file that claims to be a PDF but contains only plain text.
    response = _upload(
        client, project["id"], "fake.pdf", b"this is plainly text, not a pdf", "application/pdf", auth_headers
    )
    body = response.json()
    assert body["failed"] == 1
    assert "does not match" in body["results"][0]["message"]


def test_empty_file_is_rejected(client, project, auth_headers) -> None:
    response = _upload(client, project["id"], "empty.txt", b"", "text/plain", auth_headers)
    body = response.json()
    assert body["failed"] == 1


def test_oversized_upload_is_rejected(client, project, auth_headers) -> None:
    from app.core.config import settings

    oversized = b"a" * (settings.max_upload_size_bytes + 1024)
    response = _upload(client, project["id"], "big.txt", oversized, "text/plain", auth_headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_duplicate_content_is_detected(client, project, auth_headers) -> None:
    content = "# Notes\n\nThe same knowledge, uploaded twice.\n".encode()

    first = _upload(client, project["id"], "notes.md", content, "text/markdown", auth_headers).json()
    second = _upload(client, project["id"], "notes-copy.md", content, "text/markdown", auth_headers).json()

    assert first["accepted"] == 1
    assert second["accepted"] == 0
    assert second["duplicates"] == 1
    duplicate = second["results"][0]
    assert duplicate["status"] == "duplicate"
    assert duplicate["source_id"] == first["results"][0]["source_id"]
    assert duplicate["duplicate_of"] == first["results"][0]["source_id"]


def test_listing_reports_real_counts(client, project, auth_headers, synthetic_pdf) -> None:
    _upload(client, project["id"], "handover.pdf", synthetic_pdf, "application/pdf", auth_headers)
    _upload(client, project["id"], "notes.md", b"# Notes\n\nhello\n", "text/markdown", auth_headers)

    response = client.get(f"/api/v1/projects/{project['id']}/sources", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["total"] == 2
    assert body["type_counts"]["uploaded_pdf"] == 1
    assert body["type_counts"]["uploaded_markdown"] == 1
    assert body["status_counts"]["completed"] == 2
