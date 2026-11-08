"""Phase 5 §15 — end-to-end acceptance test for the CONTINUUM backend.

This module walks the *entire* product workflow the specification describes,
against the real HTTP stack and a real PostgreSQL database, in the order a real
team would use it:

    workspace → project → ingest sources → reconstruct memory → human review →
    conflict resolution → handover lifecycle → export → readiness → missing
    knowledge → successor tasks → knowledge dependencies → successor workspace →
    scorecard → successor exercise → evaluation → audit → tenant isolation.

The only thing that is doubled is the **model**: ``get_llm_provider`` is
overridden with :class:`tests.fake_provider.FakeProvider` driven by
:func:`tests.synthetic_project.typed_respond`. That double is deterministic and
offline; it is never presented as evidence of live model performance. Every
other moving part — the ingestion pipeline, the reconstruction graph, the review
state machine, the approval engine, conflict resolution, handover versioning,
export, the readiness/knowledge/successor/continuity engines and the audit
trail — is the production code path.

The test asserts the *honest contract*, not a happy-path illusion:

* only human-**approved** claims count toward readiness and the handover;
* a claim the AI produced can never reach ``Verified`` without a human;
* no endpoint invents data (the GitHub integration reports its unconfigured
  boundary rather than fabricating repositories).
"""

from __future__ import annotations

import uuid

import pytest

from app.main import app
from app.models.project import Project
from fake_provider import FakeProvider
from synthetic_project import seed_synthetic_project, typed_respond

import app.api.v1.memory as memory_api

#: Metric keys the evaluation framework computes (``app/evaluation/metrics.py``).
_METRIC_KEYS = {
    "A_claim_extraction",
    "B_evidence_accuracy",
    "C_verification_accuracy",
    "D_conflict_detection",
    "E_stale_detection",
    "F_critical_knowledge_coverage",
    "G_unsupported_handover_rate",
    "H_permission_leakage",
    "I_readiness_agreement",
}

#: Sections A–J of the successor workspace (§4).
_WORKSPACE_SECTION_KEYS = [
    "start_here",
    "project_overview",
    "key_decisions",
    "technical_architecture",
    "responsibilities",
    "current_work",
    "risks_and_blockers",
    "operational_procedures",
    "open_questions",
    "first_actions",
]

_VALID_BANDS = {"strong", "mostly_ready", "needs_review", "not_ready"}


# ---------------------------------------------------------------------------
# Model override helpers (the exact mechanism the existing tests use)
# ---------------------------------------------------------------------------
def _override_provider(provider) -> None:
    app.dependency_overrides[memory_api.get_llm_provider] = lambda: provider


def _clear_provider() -> None:
    app.dependency_overrides.pop(memory_api.get_llm_provider, None)


def _reconstruct(client, project_id, provider, headers) -> dict:
    _override_provider(provider)
    try:
        response = client.post(
            f"/api/v1/projects/{project_id}/memory/reconstruct",
            json={},
            headers=headers,
        )
    finally:
        _clear_provider()
    assert response.status_code == 201, response.text
    return response.json()


def _generate_handover(client, project_id, headers) -> dict:
    _override_provider(FakeProvider(typed_respond))
    try:
        response = client.post(
            f"/api/v1/projects/{project_id}/handovers/generate", headers=headers
        )
    finally:
        _clear_provider()
    assert response.status_code == 201, response.text
    return response.json()


def _claim_detail(client, project_id, claim_id, headers) -> dict:
    response = client.get(
        f"/api/v1/projects/{project_id}/claims/{claim_id}", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def _conflict_free_supported_claims(client, project_id, headers) -> list[dict]:
    """Supported claims that are *not* part of an undecided conflict.

    Phase 4 forbids approving a claim while a conflict it belongs to is open, so
    the acceptance flow may only approve claims a reviewer could actually approve.
    """
    listing = client.get(
        f"/api/v1/projects/{project_id}/claims",
        params={"status": "Supported", "page_size": 100},
        headers=headers,
    ).json()
    approvable: list[dict] = []
    for claim in listing["items"]:
        detail = _claim_detail(client, project_id, claim["id"], headers)
        if not any(item["status"] == "open" for item in detail["conflicts"]):
            approvable.append(claim)
    return approvable


def _approve_all_conflict_free(client, project_id, headers) -> list[dict]:
    """Approve every claim a reviewer legitimately could; return the approved ones."""
    approved: list[dict] = []
    for claim in _conflict_free_supported_claims(client, project_id, headers):
        response = client.post(
            f"/api/v1/projects/{project_id}/claims/{claim['id']}/approve",
            json={"explanation": "Reviewed and approved during the acceptance run."},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "Verified"
        assert body["review_status"] == "Approved"
        approved.append(body)
    return approved


# ---------------------------------------------------------------------------
# The single, ordered end-to-end acceptance test
# ---------------------------------------------------------------------------
def test_full_continuum_workflow_end_to_end(
    client,
    db_session,
    workspace,
    project,
    auth_headers,
    synthetic_pdf,
    foreign_workspace,
) -> None:
    project_id = project["id"]

    # ------------------------------------------------------------------
    # 1–2. The workspace and project exist (created by the fixtures above).
    # ------------------------------------------------------------------
    assert workspace["id"] and workspace["name"]
    assert project["workspace_id"] == workspace["id"]
    assert project["id"]

    # ------------------------------------------------------------------
    # 3. Attach source records.
    # ------------------------------------------------------------------
    # 3a. A real document, uploaded through the real ingestion endpoint.
    upload = client.post(
        f"/api/v1/projects/{project_id}/sources/upload",
        files=[("files", ("runbook.pdf", synthetic_pdf, "application/pdf"))],
        headers=auth_headers,
    )
    assert upload.status_code == 201, upload.text
    upload_body = upload.json()
    assert upload_body["accepted"] == 1
    assert upload_body["failed"] == 0
    uploaded = upload_body["results"][0]
    assert uploaded["status"] == "completed"
    assert uploaded["source_id"]

    # The upload is read back from PostgreSQL — nothing is invented.
    sources = client.get(
        f"/api/v1/projects/{project_id}/sources", headers=auth_headers
    ).json()
    assert uploaded["source_id"] in {item["id"] for item in sources["items"]}
    assert sources["meta"]["total"] >= 1

    # 3b. GitHub is exercised as its documented boundary: when credentials are
    # absent the server reports the boundary honestly instead of faking repos.
    boundary = client.get("/api/v1/github/boundary", headers=auth_headers)
    assert boundary.status_code == 200, boundary.text
    boundary_body = boundary.json()
    assert isinstance(boundary_body["configured"], bool)
    connect = client.post("/api/v1/github/connect", headers=auth_headers)
    if boundary_body["configured"]:
        assert connect.status_code == 200, connect.text
        assert connect.json()["authorize_url"]
    else:
        assert connect.status_code == 503, connect.text
        assert connect.json()["error"]["code"] == "github_not_configured"
        assert boundary_body["remediation"], "the boundary must explain how to configure it"

    # 3c. The deterministic synthetic corpus (real rows, written to PostgreSQL)
    # supplies the conflicts/staleness signals the downstream engines rely on.
    seeded = seed_synthetic_project(db_session, uuid.UUID(project_id))
    db_session.commit()
    assert len(seeded) == 4

    # ------------------------------------------------------------------
    # 4–5. Reconstruct the project memory with the deterministic model double.
    # ------------------------------------------------------------------
    reconstructed = _reconstruct(client, project_id, FakeProvider(typed_respond), auth_headers)
    assert reconstructed["status"] == "completed", reconstructed
    assert reconstructed["claim_count"] > 0
    assert reconstructed["source_count"] == 5  # 4 synthetic + 1 uploaded
    # A model verdict can never reach Verified: only a human review can.
    assert reconstructed["verified_count"] == 0
    assert reconstructed["stats"]["span_count"] > 0

    claims = client.get(
        f"/api/v1/projects/{project_id}/claims",
        params={"page_size": 100},
        headers=auth_headers,
    ).json()
    assert claims["meta"]["total"] == reconstructed["claim_count"]
    assert "Verified" not in claims["status_counts"]

    # Evidence is real and traceable on every extracted claim.
    for claim in claims["items"]:
        detail = _claim_detail(client, project_id, claim["id"], auth_headers)
        assert detail["evidence"], f"claim {claim['id']} carries no evidence"
        for ref in detail["evidence"]:
            assert ref["span_id"] and ref["supporting_quote"] and ref["source_name"]

    # ------------------------------------------------------------------
    # 6. Approve claims as a human.
    # ------------------------------------------------------------------
    approved = _approve_all_conflict_free(client, project_id, auth_headers)
    assert approved, "at least one conflict-free claim must be approvable"
    approved_texts = [item["text"] for item in approved]

    verified = client.get(
        f"/api/v1/projects/{project_id}/claims",
        params={"status": "Verified", "page_size": 100},
        headers=auth_headers,
    ).json()
    assert verified["meta"]["total"] == len(approved)

    # ------------------------------------------------------------------
    # 7. Resolve the conflicts the reconstruction produced.
    # ------------------------------------------------------------------
    conflicts = client.get(
        f"/api/v1/projects/{project_id}/conflicts",
        params={"page_size": 100},
        headers=auth_headers,
    ).json()
    kinds = {item["kind"] for item in conflicts["items"]}
    assert "value_disagreement" in kinds, conflicts["items"]

    open_conflicts = [item for item in conflicts["items"] if item["status"] == "open"]
    assert open_conflicts, "the deterministic corpus must surface an undecided conflict"
    for conflict in open_conflicts:
        detail = client.get(
            f"/api/v1/projects/{project_id}/conflicts/{conflict['id']}",
            headers=auth_headers,
        ).json()
        assert len(detail["claims"]) >= 2
        chosen = detail["claims"][0]["id"]
        resolved = client.post(
            f"/api/v1/projects/{project_id}/conflicts/{conflict['id']}/resolve",
            json={
                "resolution": "claim_a_accepted",
                "note": "The newer, more authoritative source wins.",
                "chosen_claim_id": chosen,
            },
            headers=auth_headers,
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "resolved"

    # Resolving a conflict unblocks the accepted claim; a reviewer may now
    # approve it (and the ones it freed) — approvals only ever come from a human.
    approved += _approve_all_conflict_free(client, project_id, auth_headers)
    approved_texts = [item["text"] for item in approved]

    # ------------------------------------------------------------------
    # 8–9. Generate a handover and take it through its lifecycle.
    # ------------------------------------------------------------------
    generated = _generate_handover(client, project_id, auth_headers)
    handover_id = generated["id"]
    assert generated["current"]["version_number"] == 1
    assert generated["current"]["status"] == "Draft"
    assert generated["current"]["included_claim_ids"], "the handover must cite approved claims"
    assert set(generated["current"]["included_claim_ids"]) <= {
        item["id"] for item in approved
    }

    submitted = client.post(
        f"/api/v1/projects/{project_id}/handovers/{handover_id}/submit",
        headers=auth_headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "In Review"

    handover_approved = client.post(
        f"/api/v1/projects/{project_id}/handovers/{handover_id}/approve",
        json={"note": "Reviewed and approved."},
        headers=auth_headers,
    )
    assert handover_approved.status_code == 200, handover_approved.text
    assert handover_approved.json()["status"] == "Approved"

    published = client.post(
        f"/api/v1/projects/{project_id}/handovers/{handover_id}/publish",
        headers=auth_headers,
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "Published"

    # ------------------------------------------------------------------
    # 10. Export the handover as Markdown and check the approved statement.
    # ------------------------------------------------------------------
    markdown = client.get(
        f"/api/v1/projects/{project_id}/handovers/{handover_id}/export.md",
        headers=auth_headers,
    )
    assert markdown.status_code == 200, markdown.text
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert approved_texts
    assert any(text in markdown.text for text in approved_texts), (
        "the exported handover must contain an approved statement"
    )

    # ------------------------------------------------------------------
    # 11. Run the readiness engine and confirm the snapshot is persisted.
    # ------------------------------------------------------------------
    readiness = client.post(
        f"/api/v1/projects/{project_id}/readiness/evaluate", json={}, headers=auth_headers
    )
    assert readiness.status_code == 201, readiness.text
    readiness_body = readiness.json()
    assert isinstance(readiness_body["overall_score"], float)
    assert 0.0 <= readiness_body["overall_score"] <= 100.0
    assert readiness_body["band"] in _VALID_BANDS
    assert readiness_body["dimension_scores"]
    assert isinstance(readiness_body["blockers"], list)
    assert isinstance(readiness_body["warnings"], list)
    assert readiness_body["requirements"]

    history = client.get(
        f"/api/v1/projects/{project_id}/readiness/history", headers=auth_headers
    ).json()
    assert history["total"] >= 1
    assert readiness_body["id"] in {item["id"] for item in history["items"]}

    # ------------------------------------------------------------------
    # 12. Detect missing knowledge (derived from the readiness requirements).
    # ------------------------------------------------------------------
    gaps = client.post(
        f"/api/v1/projects/{project_id}/knowledge-gaps/detect", headers=auth_headers
    )
    assert gaps.status_code == 200, gaps.text
    gaps_body = gaps.json()
    assert gaps_body["total"] >= 1
    valid_gap_statuses = {"Open", "In Progress", "Resolved", "Accepted Risk"}
    for gap in gaps_body["items"]:
        assert gap["gap_key"]
        assert gap["status"] in valid_gap_statuses

    # ------------------------------------------------------------------
    # 13. Derive successor tasks, update one, and confirm the audit trail.
    # ------------------------------------------------------------------
    derived = client.post(
        f"/api/v1/projects/{project_id}/successor-tasks/derive", headers=auth_headers
    )
    assert derived.status_code == 200, derived.text
    derived_body = derived.json()
    assert derived_body["total"] >= 1
    assert derived_body["created"] >= 1

    tasks = client.get(
        f"/api/v1/projects/{project_id}/successor-tasks", headers=auth_headers
    ).json()
    assert tasks["total"] >= 1
    task = tasks["items"][0]
    assert task["status"] == "Not Started"

    updated = client.patch(
        f"/api/v1/projects/{project_id}/successor-tasks/{task['id']}",
        json={"status": "In Progress", "note": "Successor picked this up."},
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "In Progress"

    status_history = client.get(
        f"/api/v1/projects/{project_id}/audit",
        params={"action": "successor_task_status_changed"},
        headers=auth_headers,
    ).json()
    entry = next(
        item
        for item in status_history["items"]
        if item["metadata"].get("to") == "In Progress"
        and item["resource_id"] == task["id"]
    )
    assert entry["metadata"]["from"] == "Not Started"

    # ------------------------------------------------------------------
    # 14. Analyse the knowledge concentration (dependencies).
    # ------------------------------------------------------------------
    dependencies = client.post(
        f"/api/v1/projects/{project_id}/knowledge-dependencies/analyse",
        headers=auth_headers,
    )
    assert dependencies.status_code == 200, dependencies.text
    dependencies_body = dependencies.json()
    assert dependencies_body["total"] == len(dependencies_body["items"])
    assert dependencies_body["total"] >= 1
    for item in dependencies_body["items"]:
        assert item["entity"]
        assert isinstance(item["involved_people"], list)
        assert item["risk_status"] in {"Low", "Moderate", "High", "Unknown"}
    assert any(item["involved_people"] for item in dependencies_body["items"]), (
        "an approved ownership claim with sourced authorship must yield a dependency"
    )

    # ------------------------------------------------------------------
    # 15. Read the successor workspace (sections A–J).
    # ------------------------------------------------------------------
    successor_workspace = client.get(
        f"/api/v1/projects/{project_id}/successor-workspace", headers=auth_headers
    )
    assert successor_workspace.status_code == 200, successor_workspace.text
    workspace_body = successor_workspace.json()
    assert workspace_body["project_id"] == project_id
    section_keys = [section["key"] for section in workspace_body["sections"]]
    assert section_keys == _WORKSPACE_SECTION_KEYS, section_keys
    assert workspace_body["sections"][0]["narrative"]
    assert workspace_body["counts"]["approved_claims"] == len(approved)
    assert workspace_body["handover"]["published_version_number"] == 1
    assert workspace_body["disclaimer"]

    # ------------------------------------------------------------------
    # 16. Read the continuity scorecard (documented keys).
    # ------------------------------------------------------------------
    scorecard = client.get(
        f"/api/v1/projects/{project_id}/scorecard", headers=auth_headers
    )
    assert scorecard.status_code == 200, scorecard.text
    card = scorecard.json()
    assert card["project_id"] == project_id
    assert "overall_score" in card["handover_readiness"]
    assert "blocker_count" in card["handover_readiness"]
    assert "open" in card["conflicts"] and "total" in card["conflicts"]
    assert "open" in card["missing_knowledge"]
    assert "high_risk" in card["knowledge_dependencies"]
    assert "total" in card["successor_tasks"]
    assert "total_sources" in card["source_coverage"]
    assert card["generated_at"]

    # ------------------------------------------------------------------
    # 17. Run the successor readiness exercise.
    # ------------------------------------------------------------------
    exercise = client.post(
        f"/api/v1/projects/{project_id}/successor-exercise", headers=auth_headers
    )
    assert exercise.status_code == 201, exercise.text
    exercise_body = exercise.json()
    assert exercise_body["kind"] == "successor_exercise"
    metrics = exercise_body["metrics"]
    assert isinstance(metrics["tasks_attempted"], int)
    assert isinstance(metrics["tasks_completed"], int)
    assert metrics["tasks_attempted"] >= 1
    assert 0 <= metrics["tasks_completed"] <= metrics["tasks_attempted"]
    assert len(exercise_body["report"]["questions"]) == metrics["tasks_attempted"]

    # ------------------------------------------------------------------
    # 18. Run the reproducible metrics evaluation and confirm persistence.
    # ------------------------------------------------------------------
    evaluation = client.post(
        f"/api/v1/projects/{project_id}/evaluation/runs", json={}, headers=auth_headers
    )
    assert evaluation.status_code == 201, evaluation.text
    evaluation_body = evaluation.json()
    assert evaluation_body["kind"] == "metrics"
    assert _METRIC_KEYS.issubset(evaluation_body["metrics"])
    assert _METRIC_KEYS.issubset(evaluation_body["report"])

    runs = client.get(
        f"/api/v1/projects/{project_id}/evaluation/runs", headers=auth_headers
    ).json()
    assert runs["total"] >= 2  # the successor exercise + this metrics run
    assert evaluation_body["id"] in {item["id"] for item in runs["items"]}

    # ------------------------------------------------------------------
    # 19. Inspect the immutable audit trail.
    # ------------------------------------------------------------------
    trail = client.get(
        f"/api/v1/projects/{project_id}/audit",
        params={"page_size": 200},
        headers=auth_headers,
    ).json()
    actions = {item["action"] for item in trail["items"]}
    assert {
        "claim_approved",
        "conflict_resolved",
        "handover_generated",
        "handover_version_created",
        "handover_submitted",
        "handover_approved",
        "handover_published",
        "handover_exported",
        "readiness_evaluated",
        "knowledge_gaps_detected",
        "successor_tasks_derived",
        "successor_task_status_changed",
        "knowledge_dependencies_analysed",
        "successor_exercise_run",
    } <= actions
    for item in trail["items"]:
        assert item["action"]
        assert item["metadata"].get("project_id") == project_id

    # ------------------------------------------------------------------
    # 20. Tenant isolation: a foreign workspace sees nothing (404, not 403).
    # ------------------------------------------------------------------
    foreign_project = Project(
        workspace_id=uuid.UUID(foreign_workspace["id"]), name="Someone else's project"
    )
    db_session.add(foreign_project)
    db_session.commit()

    isolated = [
        ("get", f"/api/v1/projects/{foreign_project.id}/readiness"),
        ("get", f"/api/v1/projects/{foreign_project.id}/scorecard"),
        ("get", f"/api/v1/projects/{foreign_project.id}/successor-workspace"),
        ("post", f"/api/v1/projects/{foreign_project.id}/readiness/evaluate"),
    ]
    for method, url in isolated:
        response = getattr(client, method)(url, headers=auth_headers)
        assert response.status_code == 404, (url, response.status_code, response.text)


if __name__ == "__main__":  # pragma: no cover - convenience for manual runs
    pytest.main([__file__, "-q"])
