"""Security controls: archive traversal, deny lists, secret scanning/redaction."""

from __future__ import annotations

from app.services.security_scanner import scan_text


def _upload(client, project_id, filename, payload, content_type, headers):
    return client.post(
        f"/api/v1/projects/{project_id}/sources/upload",
        files=[("files", (filename, payload, content_type))],
        headers=headers,
    )


# ---------------------------------------------------------------------------
# ZIP safety
# ---------------------------------------------------------------------------
def test_zip_slip_entry_is_rejected_but_safe_entries_ingest(
    client, project, auth_headers, zip_builder
) -> None:
    payload = zip_builder(
        {
            "../escape.md": b"# Escaped\n\nshould never be ingested\n",
            "notes.md": b"# Safe\n\nlegitimate knowledge\n",
        }
    )
    response = _upload(client, project["id"], "bundle.zip", payload, "application/zip", auth_headers)
    assert response.status_code == 201, response.text
    body = response.json()

    by_name = {item["filename"]: item for item in body["results"]}
    assert by_name["../escape.md"]["status"] == "failed"
    assert "Unsafe archive path" in by_name["../escape.md"]["message"]
    assert by_name["notes.md"]["status"] == "completed"
    assert by_name["notes.md"]["source_type"] == "uploaded_zip_entry"
    assert body["accepted"] == 1


def test_zip_denied_paths_and_nested_archives_are_skipped(
    client, project, auth_headers, zip_builder
) -> None:
    inner = zip_builder({"deep.md": b"# Deep\n"})
    payload = zip_builder(
        {
            "node_modules/pkg/index.md": b"# Dep\n",
            ".env": b"SECRET_TOKEN=abc\n",
            "inner.zip": inner,
            "docs/guide.md": b"# Guide\n\nuseful\n",
        }
    )
    response = _upload(client, project["id"], "repo.zip", payload, "application/zip", auth_headers)
    assert response.status_code == 201, response.text
    body = response.json()

    by_name = {item["filename"]: item for item in body["results"]}
    assert by_name["node_modules/pkg/index.md"]["status"] == "skipped"
    assert "deny list" in by_name["node_modules/pkg/index.md"]["message"].lower()
    assert by_name["inner.zip"]["status"] == "skipped"
    assert "Nested archives" in by_name["inner.zip"]["message"]
    assert by_name[".env"]["status"] == "skipped"
    # Completed archive entries are stored under their basename.
    assert by_name["guide.md"]["status"] == "completed"


def test_absolute_archive_path_is_rejected(client, project, auth_headers, zip_builder) -> None:
    payload = zip_builder({"/etc/passwd": b"root:x:0:0\n"})
    response = _upload(client, project["id"], "abs.zip", payload, "application/zip", auth_headers)
    body = response.json()
    assert body["failed"] == 1
    assert "Unsafe archive path" in body["results"][0]["message"]


# ---------------------------------------------------------------------------
# Secret scanning
# ---------------------------------------------------------------------------
def test_scanner_redacts_without_leaking_values() -> None:
    raw = 'api_key = "supersecretvalue123"\n'
    result = scan_text(raw)
    assert result.has_secrets
    assert "supersecretvalue123" not in result.redacted_content
    assert "[REDACTED:" in result.redacted_content
    # Findings carry only a masked preview, never the raw value.
    for finding in result.findings:
        assert "supersecretvalue123" not in finding.masked_preview
        assert "supersecretvalue123" not in finding.as_warning()


def test_scanner_leaves_benign_text_untouched() -> None:
    result = scan_text("The invoice service owns billing.")
    assert not result.has_secrets
    assert result.redacted_content == "The invoice service owns billing."


def test_uploaded_secret_is_redacted_before_storage(client, project, auth_headers) -> None:
    content = (
        "# Configuration\n\n"
        "GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789\n"
        '\npassword = "hunter2hunter2hunter2"\n'
    ).encode()
    response = _upload(client, project["id"], "config.md", content, "text/markdown", auth_headers)
    assert response.status_code == 201, response.text
    result = response.json()["results"][0]
    assert result["status"] == "completed"
    assert result["warnings"], "a redaction warning must be recorded"

    detail = client.get(f"/api/v1/sources/{result['source_id']}", headers=auth_headers).json()
    stored = detail["content"]
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in stored
    assert "hunter2hunter2hunter2" not in stored
    assert "[REDACTED:" in stored
    assert detail["metadata"]["security_scan"]["has_secrets"] is True
