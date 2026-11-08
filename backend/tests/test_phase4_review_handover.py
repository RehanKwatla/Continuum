"""Phase 4 end-to-end tests: review, approval, conflicts and handover.

These tests drive the real API against real PostgreSQL. Only the model is
doubled (:class:`tests.fake_provider.FakeProvider`); the review state machine,
the approval engine, conflict resolution, handover versioning, export and the
audit trail are all the production code paths.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.main import app
from app.models.claim import Claim
from app.models.enums import ClaimStatus, ClaimType, WorkspaceRole
from app.models.workspace import WorkspaceMember
from fake_provider import FakeProvider
from synthetic_project import seed_synthetic_project, typed_respond

import app.api.v1.memory as memory_api


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------
def _override_provider(provider) -> None:
    app.dependency_overrides[memory_api.get_llm_provider] = lambda: provider


def _clear_provider() -> None:
    app.dependency_overrides.pop(memory_api.get_llm_provider, None)


def reconstruct(client, project_id, provider, headers):
    _override_provider(provider)
    try:
        return client.post(
            f"/api/v1/projects/{project_id}/memory/reconstruct", json={}, headers=headers
        )
    finally:
        _clear_provider()


@pytest.fixture
def seeded(db_session, project) -> dict[str, uuid.UUID]:
    ids = seed_synthetic_project(db_session, uuid.UUID(project["id"]))
    db_session.commit()
    return ids


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider(typed_respond)


@pytest.fixture
def reconstructed(client, seeded, project, auth_headers, provider) -> dict:
    response = reconstruct(client, project["id"], provider, auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


def _approvable_claim(client, project_id, headers) -> dict:
    """A supported claim that is not part of an undecided conflict."""
    listing = client.get(
        f"/api/v1/projects/{project_id}/claims",
        params={"status": "Supported", "page_size": 100},
        headers=headers,
    ).json()
    for claim in listing["items"]:
        detail = client.get(
            f"/api/v1/projects/{project_id}/claims/{claim['id']}", headers=headers
        ).json()
        if not any(item["status"] == "open" for item in detail["conflicts"]):
            return claim
    raise AssertionError("no claim outside an open conflict was produced")


def _open_conflict(client, project_id, headers) -> dict:
    """The first *undecided* conflict (change-over-time findings are pre-dismissed)."""
    listing = client.get(
        f"/api/v1/projects/{project_id}/conflicts",
        params={"status": "open", "page_size": 100},
        headers=headers,
    ).json()
    assert listing["items"], "the reconstruction must surface an open conflict"
    return listing["items"][0]


def _approve(client, project_id, claim_id, headers) -> None:
    response = client.post(
        f"/api/v1/projects/{project_id}/claims/{claim_id}/approve",
        json={"explanation": "Approved during review."},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Verified"


def _generate_handover(client, project_id, headers, provider=None) -> dict:
    _override_provider(provider or FakeProvider(typed_respond))
    try:
        response = client.post(
            f"/api/v1/projects/{project_id}/handovers/generate", headers=headers
        )
    finally:
        _clear_provider()
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# §3 Human review queue
# ---------------------------------------------------------------------------
def test_review_queue_reports_verification_and_approval_separately(
    client, project, auth_headers, reconstructed
) -> None:
    queue = client.get(
        f"/api/v1/projects/{project['id']}/review-queue",
        params={"page_size": 100},
        headers=auth_headers,
    ).json()

    assert queue["meta"]["total"] == reconstructed["claim_count"]
    items = {item["id"]: item for item in queue["items"]}
    assert items, "the queue must list the extracted claims"

    sample = queue["items"][0]
    # The AI verdict and the human review status are distinct fields.
    assert sample["ai_verdict"] in {"supports", "partly", "none", None}
    assert sample["review_status"] in {
        "Extracted",
        "Supported",
        "Uncertain",
        "Conflict",
        "Pending review",
        "Needs clarification",
        "Rejected",
        "Approved",
    }
    assert sample["evidence_count"] >= 1
    assert sample["source_references"]
    assert sample["conflict_status"] in {"clear", "open", "resolved"}
    assert sample["revision_number"] == 1

    # Filters.
    approved = client.get(
        f"/api/v1/projects/{project['id']}/review-queue",
        params={"status": "approved"},
        headers=auth_headers,
    ).json()
    assert approved["items"] == []

    critical = client.get(
        f"/api/v1/projects/{project['id']}/review-queue",
        params={"status": "critical", "page_size": 100},
        headers=auth_headers,
    ).json()
    assert critical["items"]
    assert all(item["critical"] for item in critical["items"])

    # Sorting + pagination.
    oldest = client.get(
        f"/api/v1/projects/{project['id']}/review-queue",
        params={"order": "oldest", "page_size": 100},
        headers=auth_headers,
    ).json()
    created = [item["created_at"] for item in oldest["items"]]
    assert created == sorted(created)

    paged = client.get(
        f"/api/v1/projects/{project['id']}/review-queue",
        params={"page": 1, "page_size": 2},
        headers=auth_headers,
    ).json()
    assert len(paged["items"]) == 2


# ---------------------------------------------------------------------------
# §5, §7 Approval engine
# ---------------------------------------------------------------------------
def test_approval_requires_traceable_evidence(
    client, db_session, project, auth_headers, reconstructed
) -> None:
    orphan = Claim(
        project_id=uuid.UUID(project["id"]),
        text="An unevidenced assertion.",
        claim_type=ClaimType.RISK,
        status=ClaimStatus.SUPPORTED,
    )
    db_session.add(orphan)
    db_session.commit()

    response = client.post(
        f"/api/v1/projects/{project['id']}/claims/{orphan.id}/approve",
        json={"explanation": "Looks fine."},
        headers=auth_headers,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "evidence_required"


def test_approval_is_blocked_by_an_open_conflict(
    client, project, auth_headers, reconstructed
) -> None:
    conflicts = client.get(
        f"/api/v1/projects/{project['id']}/conflicts", headers=auth_headers
    ).json()["items"]
    open_conflict = next(item for item in conflicts if item["status"] == "open")
    claim_id = open_conflict["claims"][0]["id"]

    response = client.post(
        f"/api/v1/projects/{project['id']}/claims/{claim_id}/approve",
        json={"explanation": "Ignoring the conflict."},
        headers=auth_headers,
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "conflict"


def test_edited_revision_cannot_be_approved_until_verified(
    client, project, auth_headers, reconstructed
) -> None:
    claim = _approvable_claim(client, project["id"], auth_headers)
    edited = client.post(
        f"/api/v1/projects/{project['id']}/claims/{claim['id']}/edit",
        json={"text": "A materially rewritten statement.", "note": "Correction."},
        headers=auth_headers,
    )
    assert edited.status_code == 200, edited.text

    blocked = client.post(
        f"/api/v1/projects/{project['id']}/claims/{claim['id']}/approve",
        json={"explanation": "Approve the edit."},
        headers=auth_headers,
    )
    assert blocked.status_code == 422, blocked.text
    assert blocked.json()["error"]["code"] == "verification_required"

    # After the model re-verifies the new revision, a reviewer may approve it.
    _override_provider(FakeProvider(typed_respond))
    try:
        verified = client.post(
            f"/api/v1/projects/{project['id']}/claims/{claim['id']}/verify",
            headers=auth_headers,
        )
    finally:
        _clear_provider()
    assert verified.status_code == 200, verified.text

    _approve(client, project["id"], claim["id"], auth_headers)


def test_a_viewer_cannot_approve_a_claim(
    client, db_session, project, auth_headers, reconstructed
) -> None:
    membership = db_session.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == uuid.UUID(project["workspace_id"])
        )
    ).scalar_one()
    membership.role = WorkspaceRole.VIEWER
    db_session.commit()

    claim = _approvable_claim(client, project["id"], auth_headers)
    response = client.post(
        f"/api/v1/projects/{project['id']}/claims/{claim['id']}/approve",
        json={"explanation": "Should not be allowed."},
        headers=auth_headers,
    )
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# §6 Conflict Resolution Centre
# ---------------------------------------------------------------------------
def test_conflict_detail_shows_both_sides_with_evidence(
    client, project, auth_headers, reconstructed
) -> None:
    conflict = _open_conflict(client, project["id"], auth_headers)

    detail = client.get(
        f"/api/v1/projects/{project['id']}/conflicts/{conflict['id']}", headers=auth_headers
    ).json()
    assert detail["id"] == conflict["id"]
    assert len(detail["claims"]) >= 2
    for side in detail["claims"]:
        assert side["text"]
        assert side["status"]
        assert side["evidence"], "both sides must expose their supporting evidence"


def test_more_information_required_keeps_the_conflict_open(
    client, project, auth_headers, reconstructed
) -> None:
    conflict = _open_conflict(client, project["id"], auth_headers)

    response = client.post(
        f"/api/v1/projects/{project['id']}/conflicts/{conflict['id']}/resolve",
        json={
            "resolution": "more_information_required",
            "note": "We need the original migration plan.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "open"


def test_rejecting_both_claims_preserves_them(
    client, project, auth_headers, reconstructed
) -> None:
    conflict = _open_conflict(client, project["id"], auth_headers)
    claim_ids = [item["id"] for item in conflict["claims"]]

    response = client.post(
        f"/api/v1/projects/{project['id']}/conflicts/{conflict['id']}/resolve",
        json={"resolution": "both_rejected", "note": "Neither statement is reliable."},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "resolved"

    # The claims are preserved (not deleted) and now rejected.
    for claim_id in claim_ids:
        detail = client.get(
            f"/api/v1/projects/{project['id']}/claims/{claim_id}", headers=auth_headers
        ).json()
        assert detail["status"] == "Rejected"
        assert detail["evidence"]


def test_accepting_one_side_requires_naming_it(
    client, project, auth_headers, reconstructed
) -> None:
    conflict = _open_conflict(client, project["id"], auth_headers)

    response = client.post(
        f"/api/v1/projects/{project['id']}/conflicts/{conflict['id']}/resolve",
        json={"resolution": "claim_a_accepted", "note": "This one is right."},
        headers=auth_headers,
    )
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# §8–§12 Handover generation, lifecycle and versioning
# ---------------------------------------------------------------------------
def test_handover_full_lifecycle_and_versioning(
    client, project, auth_headers, reconstructed
) -> None:
    claim = _approvable_claim(client, project["id"], auth_headers)
    _approve(client, project["id"], claim["id"], auth_headers)

    generated = _generate_handover(client, project["id"], auth_headers)
    handover_id = generated["id"]
    assert generated["current"]["version_number"] == 1
    assert generated["current"]["status"] == "Draft"

    submitted = client.post(
        f"/api/v1/projects/{project['id']}/handovers/{handover_id}/submit",
        headers=auth_headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "In Review"

    approved = client.post(
        f"/api/v1/projects/{project['id']}/handovers/{handover_id}/approve",
        json={"note": "Reviewed and approved."},
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "Approved"

    published = client.post(
        f"/api/v1/projects/{project['id']}/handovers/{handover_id}/publish",
        headers=auth_headers,
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "Published"

    # Editing a published handover starts a new draft and never overwrites v1.
    edited = client.patch(
        f"/api/v1/projects/{project['id']}/handovers/{handover_id}",
        json={
            "sections": [
                {
                    "key": "overview",
                    "title": "Project overview",
                    "statements": [
                        {
                            "text": claim["text"],
                            "claim_ids": [claim["id"]],
                        }
                    ],
                }
            ],
            "reviewer_notes": ["Verify the release process with the platform team."],
            "note": "Tightened the overview.",
        },
        headers=auth_headers,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["version_number"] == 2
    assert edited.json()["status"] == "Draft"
    assert edited.json()["reviewer_notes"]

    versions = client.get(
        f"/api/v1/projects/{project['id']}/handovers/{handover_id}/versions",
        headers=auth_headers,
    ).json()
    assert [item["version_number"] for item in versions] == [2, 1]

    first = client.get(
        f"/api/v1/projects/{project['id']}/handovers/{handover_id}/versions/1",
        headers=auth_headers,
    ).json()
    assert first["status"] == "Published", "a published version is immutable"


def test_handover_edit_flags_unsupported_factual_edits(
    client, project, auth_headers, reconstructed
) -> None:
    claim = _approvable_claim(client, project["id"], auth_headers)
    _approve(client, project["id"], claim["id"], auth_headers)
    generated = _generate_handover(client, project["id"], auth_headers)

    edited = client.patch(
        f"/api/v1/projects/{project['id']}/handovers/{generated['id']}",
        json={
            "sections": [
                {
                    "key": "overview",
                    "statements": [{"text": "An invented fact with no support.", "claim_ids": []}],
                }
            ],
            "note": "Attempt to add unsupported prose.",
        },
        headers=auth_headers,
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    statement = body["sections"][0]["statements"][0]
    assert statement["unsupported"] is True, "an unsupported fact must be flagged"
    assert any(item["code"] == "unsupported_statement" for item in body["validation_errors"])

    # A handover carrying an unsupported statement cannot be approved.
    blocked = client.post(
        f"/api/v1/projects/{project['id']}/handovers/{generated['id']}/approve",
        json={"note": "Approve anyway."},
        headers=auth_headers,
    )
    assert blocked.status_code == 422, blocked.text


def test_handover_generation_never_approves_claims(
    client, project, auth_headers, reconstructed
) -> None:
    before = client.get(
        f"/api/v1/projects/{project['id']}/claims",
        params={"status": "Verified", "page_size": 100},
        headers=auth_headers,
    ).json()
    assert before["meta"]["total"] == 0

    # No approved claims: the writer must still run and produce an honest,
    # empty document rather than inventing content.
    generated = _generate_handover(client, project["id"], auth_headers)
    assert generated["current"]["included_claim_ids"] == []

    after = client.get(
        f"/api/v1/projects/{project['id']}/claims",
        params={"status": "Verified", "page_size": 100},
        headers=auth_headers,
    ).json()
    assert after["meta"]["total"] == 0, "the writer must not approve claims"


# ---------------------------------------------------------------------------
# §14 Export
# ---------------------------------------------------------------------------
def test_handover_export_markdown_and_pdf(
    client, project, auth_headers, reconstructed
) -> None:
    claim = _approvable_claim(client, project["id"], auth_headers)
    _approve(client, project["id"], claim["id"], auth_headers)
    generated = _generate_handover(client, project["id"], auth_headers)
    handover_id = generated["id"]

    markdown = client.get(
        f"/api/v1/projects/{project['id']}/handovers/{handover_id}/export.md",
        headers=auth_headers,
    )
    assert markdown.status_code == 200, markdown.text
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert claim["text"] in markdown.text
    assert "Approval" in markdown.text

    pdf = client.get(
        f"/api/v1/projects/{project['id']}/handovers/{handover_id}/export.pdf",
        headers=auth_headers,
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


def test_export_requires_authentication(
    client, project, auth_headers, reconstructed
) -> None:
    claim = _approvable_claim(client, project["id"], auth_headers)
    _approve(client, project["id"], claim["id"], auth_headers)
    generated = _generate_handover(client, project["id"], auth_headers)

    anonymous = client.get(
        f"/api/v1/projects/{project['id']}/handovers/{generated['id']}/export.md"
    )
    assert anonymous.status_code == 401


# ---------------------------------------------------------------------------
# §15 Audit trail
# ---------------------------------------------------------------------------
def test_audit_trail_records_every_phase4_action(
    client, project, auth_headers, reconstructed
) -> None:
    claim = _approvable_claim(client, project["id"], auth_headers)
    _approve(client, project["id"], claim["id"], auth_headers)
    generated = _generate_handover(client, project["id"], auth_headers)
    handover_id = generated["id"]
    client.post(
        f"/api/v1/projects/{project['id']}/handovers/{handover_id}/submit",
        headers=auth_headers,
    )
    client.post(
        f"/api/v1/projects/{project['id']}/handovers/{handover_id}/approve",
        json={"note": "ok"},
        headers=auth_headers,
    )
    client.post(
        f"/api/v1/projects/{project['id']}/handovers/{handover_id}/publish",
        headers=auth_headers,
    )
    client.get(
        f"/api/v1/projects/{project['id']}/handovers/{handover_id}/export.md",
        headers=auth_headers,
    )

    trail = client.get(
        f"/api/v1/projects/{project['id']}/audit", params={"page_size": 200}, headers=auth_headers
    ).json()
    actions = {item["action"] for item in trail["items"]}
    assert {
        "claim_approved",
        "handover_generated",
        "handover_version_created",
        "handover_approved",
        "handover_published",
        "handover_exported",
    } <= actions

    # Every entry is attributed and stamped with the owning project.
    for item in trail["items"]:
        assert item["action"]
        assert item["metadata"].get("project_id") == project["id"]

    filtered = client.get(
        f"/api/v1/projects/{project['id']}/audit",
        params={"action": "claim_approved"},
        headers=auth_headers,
    ).json()
    assert filtered["items"]
    assert {item["action"] for item in filtered["items"]} == {"claim_approved"}
