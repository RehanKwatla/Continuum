
"""Comprehensive test suite for Continuum Public Judge Access Mode.

Validates all 15 acceptance checks demanded by the CodeZen hackathon brief:
1. Open root URL without signing in.
2. Open dashboard directly.
3. Open a project URL directly.
4. Refresh project page (stateless repeated deep link).
5. Open source library.
6. Inspect a claim.
7. Open evidence.
8. View conflicts.
9. Open handover.
10. View readiness score.
11. Verify no login redirect appears.
12. Verify no authentication token is required for public demo GET endpoints.
13. Verify private workspace data cannot be accessed.
14. Verify public visitors cannot modify protected data.
15. Verify the public demo resets to pristine seed.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import DEMO_EMAIL, DEMO_PROVIDER
import app.api.v1.repository_intelligence as repository_routes


@pytest.fixture(autouse=True)
def enable_public_demo(monkeypatch):
    """Enable public demo mode for all tests in this suite."""
    monkeypatch.setattr(settings, "public_demo_mode", True)
    monkeypatch.setattr(settings, "public_demo_read_only", True)


@pytest.fixture
def demo_data(client: TestClient) -> dict:
    """Ensure the public demo workspace is seeded for the test."""
    resp = client.get("/api/v1/public/demo")
    assert resp.status_code == 200, f"Public demo initialization failed: {resp.text}"
    data = resp.json()
    assert data["enabled"] is True
    assert data["workspace_id"] is not None
    assert data["project_id"] is not None
    return data


class TestPublicJudgeAccessMode:
    """Verifies that judges can explore the complete product without signing in."""

    def test_01_open_root_url_without_signin(self, client: TestClient):
        """Check 1: Visiting root URL returns 200 without sign-in."""
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "Continuum" in data.get("service", "")

    def test_02_open_dashboard_directly(self, client: TestClient, demo_data: dict):
        """Check 2: Open dashboard directly without signing in."""
        wid = demo_data["workspace_id"]
        resp = client.get(f"/api/v1/dashboard?workspace_id={wid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_projects"] >= 1
        assert data["total_sources"] >= 1

    def test_03_open_project_url_directly(self, client: TestClient, demo_data: dict):
        """Check 3: Open sample project directly."""
        pid = demo_data["project_id"]
        resp = client.get(f"/api/v1/projects/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == pid
        assert data["name"] == "Payment Gateway System"

    def test_04_refresh_project_page(self, client: TestClient, demo_data: dict):
        """Check 4: Deep links remain accessible on refresh without cookies/tokens."""
        pid = demo_data["project_id"]
        for _ in range(3):
            resp = client.get(f"/api/v1/projects/{pid}")
            assert resp.status_code == 200

    def test_05_open_source_library(self, client: TestClient, demo_data: dict):
        """Check 5: Open source library and list all ingested sources."""
        pid = demo_data["project_id"]
        resp = client.get(f"/api/v1/projects/{pid}/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 8
        source_names = [s["source_name"] for s in data["items"]]
        assert any("adr" in name.lower() or "readme" in name.lower() for name in source_names)

    def test_06_inspect_claim(self, client: TestClient, demo_data: dict):
        """Check 6: Inspect project claims."""
        pid = demo_data["project_id"]
        resp = client.get(f"/api/v1/projects/{pid}/claims")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 20
        claim_id = data["items"][0]["id"]

        detail_resp = client.get(f"/api/v1/projects/{pid}/claims/{claim_id}")
        assert detail_resp.status_code == 200
        claim_detail = detail_resp.json()
        assert claim_detail["id"] == claim_id
        assert len(claim_detail["text"]) > 0

    def test_07_open_evidence(self, client: TestClient, demo_data: dict):
        """Check 7: Open evidence references and inspect source details."""
        pid = demo_data["project_id"]
        sources_resp = client.get(f"/api/v1/projects/{pid}/sources")
        assert sources_resp.status_code == 200
        first_source_id = sources_resp.json()["items"][0]["id"]

        source_resp = client.get(f"/api/v1/sources/{first_source_id}")
        assert source_resp.status_code == 200
        source_data = source_resp.json()
        assert source_data["id"] == first_source_id
        assert source_data["content"] is not None

    def test_08_view_conflicts(self, client: TestClient, demo_data: dict):
        """Check 8: View conflicting architectural claims."""
        pid = demo_data["project_id"]
        resp = client.get(f"/api/v1/projects/{pid}/conflicts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 1
        conflict = data["items"][0]
        assert "postgres" in str(conflict).lower() or conflict["kind"] == "value_disagreement"

    def test_09_open_handover(self, client: TestClient, demo_data: dict):
        """Check 9: Open approved handover brief."""
        pid = demo_data["project_id"]
        resp = client.get(f"/api/v1/projects/{pid}/handovers")
        assert resp.status_code == 200
        handovers = resp.json()["items"]
        assert len(handovers) >= 1
        hid = handovers[0]["id"]

        detail_resp = client.get(f"/api/v1/projects/{pid}/handovers/{hid}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["status"] in ("Published", "Approved")
        assert "Payment Gateway" in detail["title"]

    def test_10_view_readiness_score(self, client: TestClient, demo_data: dict):
        """Check 10: View readiness scoring and successor checklist."""
        pid = demo_data["project_id"]
        resp = client.get(f"/api/v1/projects/{pid}/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["evaluation"]["overall_score"] > 80.0
        assert data["evaluation"]["band"] in ("strong", "adequate")

        scorecard_resp = client.get(f"/api/v1/projects/{pid}/scorecard")
        assert scorecard_resp.status_code == 200

        tasks_resp = client.get(f"/api/v1/projects/{pid}/successor-tasks")
        assert tasks_resp.status_code == 200
        assert len(tasks_resp.json()["items"]) >= 1

    def test_11_verify_no_login_redirect_appears(self, client: TestClient, demo_data: dict):
        """Check 11: Verify anonymous judge requests do not redirect to login (no 3xx)."""
        pid = demo_data["project_id"]
        routes = [
            "/api/v1/public/demo",
            "/api/v1/auth/me",
            "/api/v1/workspaces",
            "/api/v1/projects",
            f"/api/v1/projects/{pid}",
            f"/api/v1/projects/{pid}/sources",
            f"/api/v1/projects/{pid}/memory",
            f"/api/v1/projects/{pid}/claims",
            f"/api/v1/projects/{pid}/conflicts",
            f"/api/v1/projects/{pid}/handovers",
            f"/api/v1/projects/{pid}/readiness",
        ]
        for route in routes:
            resp = client.get(route, follow_redirects=False)
            assert resp.status_code == 200, f"Route {route} returned unexpected status {resp.status_code}"
            assert "location" not in resp.headers

    def test_12_no_authentication_token_required_for_demo(self, client: TestClient):
        """Check 12: Verify GET /auth/me returns the public-demo principal without token."""
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["auth_provider"] == DEMO_PROVIDER
        assert data["is_demo_session"] is True
        assert data["user"]["email"] == DEMO_EMAIL

    def test_13_private_workspace_data_cannot_be_accessed(self, client: TestClient):
        """Check 13: Tenant isolation - non-demo projects return 404 without leaking data."""
        random_project_id = uuid.uuid4()
        resp = client.get(f"/api/v1/projects/{random_project_id}")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_public_demo_repository_analysis_is_scoped_to_demo_project(
        self, client: TestClient, demo_data: dict, monkeypatch
    ):
        """The anonymous demo principal may analyze the seeded project only."""
        metadata = {
            "name": "sample", "owner": "continuum-demo", "description": "Demo repository",
            "canonical_url": "https://github.com/continuum-demo/sample", "default_branch": "main",
            "visibility": "public", "language": "Python", "languages": {"Python": 1000},
            "stars": 12, "forks": 2, "open_issues": 1, "created_at": None,
            "updated_at": None, "pushed_at": None, "license": "MIT",
        }
        branches = [{"name": "main", "commit_sha": "abc123", "protected": False, "is_default": True}]
        monkeypatch.setattr(repository_routes, "validate_repository_url", lambda _url: (
            SimpleNamespace(owner="continuum-demo", name="sample"), metadata, branches, "main"
        ))
        monkeypatch.setattr(repository_routes, "run_snapshot", lambda _snapshot_id: None)

        response = client.post(
            f"/api/v1/repositories/projects/{demo_data['project_id']}/analyse",
            json={"repository_url": "https://github.com/continuum-demo/sample", "branch": "main"},
        )
        assert response.status_code == 202, response.text

        private_response = client.post(
            f"/api/v1/repositories/projects/{uuid.uuid4()}/analyse",
            json={"repository_url": "https://github.com/continuum-demo/sample", "branch": "main"},
        )
        assert private_response.status_code == 404

    def test_14_public_visitors_cannot_modify_protected_data(
        self, client: TestClient, demo_data: dict
    ):
        """Check 14: Mutation guard - unauthorized writes are strictly blocked with 403."""
        pid = demo_data["project_id"]
        wid = demo_data["workspace_id"]

        # Attempt to create a project
        post_proj = client.post("/api/v1/projects", json={"workspace_id": wid, "name": "Exploit"})
        assert post_proj.status_code == 403
        assert post_proj.json()["error"]["code"] == "public_demo_read_only"

        # Attempt to modify the demo project
        patch_proj = client.patch(f"/api/v1/projects/{pid}", json={"name": "Tampered"})
        assert patch_proj.status_code == 403
        assert patch_proj.json()["error"]["code"] == "public_demo_read_only"

        # Attempt to trigger memory reconstruction
        post_recon = client.post(f"/api/v1/projects/{pid}/memory/reconstruct", json={})
        assert post_recon.status_code == 403
        assert post_recon.json()["error"]["code"] == "public_demo_read_only"

        # Attempt to generate handover
        post_handover = client.post(f"/api/v1/projects/{pid}/handovers/generate", json={})
        assert post_handover.status_code == 403
        assert post_handover.json()["error"]["code"] == "public_demo_read_only"

    def test_15_public_demo_safe_reset_action(self, client: TestClient):
        """Check 15: The single allowlisted write action (demo reset) works safely."""
        resp = client.post("/api/v1/public/demo/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["seeded"] is True
        assert data["counts"]["claims"] >= 28
