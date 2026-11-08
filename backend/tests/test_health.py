"""Health, readiness and index probes."""

from __future__ import annotations


def test_liveness_does_not_touch_database(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"]
    assert body["version"]
    assert body["environment"] == "development"


def test_health_available_under_api_prefix(client) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


def test_readiness_reports_database_ok(client) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["database"] == "ok"
    assert body["status"] == "ok"
    # Configuration posture is exposed, never secret values.
    assert "supabase_auth_configured" in body
    assert "github_oauth_configured" in body
    assert body["dev_auth_enabled"] is True


def test_root_index(client) -> None:
    response = client.get("/")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["service"]
    assert body["tagline"] == "People may leave. The knowledge shouldn't have to."
