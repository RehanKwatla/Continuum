"""End-to-end project-memory reconstruction, review and handover.

These tests exercise the real API and the real PostgreSQL persistence. The only
thing that is doubled is the **model**: ``get_llm_provider`` is overridden with
:class:`tests.fake_provider.FakeProvider` driven by
:func:`tests.synthetic_project.typed_respond`. That double is deterministic and
offline; it is never presented as evidence of live model performance.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.main import app
from app.models.project import Project
from app.schemas.memory import ReconstructRequest  # noqa: F401  (documents the body)
from fake_provider import FakeProvider
from synthetic_project import seed_synthetic_project

import app.api.v1.memory as memory_api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _override_provider(provider) -> None:
    app.dependency_overrides[memory_api.get_llm_provider] = lambda: provider


def _clear_provider() -> None:
    app.dependency_overrides.pop(memory_api.get_llm_provider, None)


def reconstruct(client, project_id, provider, headers, *, source_ids=None):
    """POST a reconstruction run with the model dependency overridden."""
    _override_provider(provider)
    try:
        payload = {"source_ids": [str(s) for s in source_ids]} if source_ids else {}
        return client.post(
            f"/api/v1/projects/{project_id}/memory/reconstruct",
            json=payload,
            headers=headers,
        )
    finally:
        _clear_provider()


@pytest.fixture
def seeded(db_session, project) -> dict[str, uuid.UUID]:
    """The synthetic project dataset, written straight into PostgreSQL."""
    ids = seed_synthetic_project(db_session, uuid.UUID(project["id"]))
    db_session.commit()
    return ids


@pytest.fixture
def provider() -> FakeProvider:
    from synthetic_project import typed_respond

    return FakeProvider(typed_respond)


# ---------------------------------------------------------------------------
# No data is invented
# ---------------------------------------------------------------------------
def test_reconstruction_without_sources_is_insufficient(client, project, auth_headers, provider) -> None:
    response = reconstruct(client, project["id"], provider, auth_headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "partial"
    assert body["claim_count"] == 0
    assert body["source_count"] == 0


def test_unreconstructed_project_invents_nothing(client, project, auth_headers) -> None:
    response = client.get(f"/api/v1/projects/{project['id']}/memory", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reconstructed"] is False
    assert body["stats"] == {}
    assert body["summary"] is None


def test_reconstruct_without_a_configured_model_records_a_failed_run(
    client, seeded, project, auth_headers
) -> None:
    _override_provider(None)
    try:
        response = client.post(
            f"/api/v1/projects/{project['id']}/memory/reconstruct",
            json={},
            headers=auth_headers,
        )
    finally:
        _clear_provider()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_not_configured"

    runs = client.get(
        f"/api/v1/projects/{project['id']}/processing-runs", headers=auth_headers
    ).json()
    assert runs["meta"]["total"] == 1
    assert runs["items"][0]["status"] == "failed"
    assert runs["items"][0]["error_message"]


# ---------------------------------------------------------------------------
# The full reconstruction
# ---------------------------------------------------------------------------
@pytest.fixture
def reconstructed(client, seeded, project, auth_headers, provider) -> dict:
    response = reconstruct(client, project["id"], provider, auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_reconstruction_produces_claims_with_traceable_evidence(
    client, project, auth_headers, reconstructed
) -> None:
    assert reconstructed["status"] == "completed", reconstructed
    assert reconstructed["claim_count"] > 0
    assert reconstructed["source_count"] == 4
    # A model verdict can never reach *Verified*: only a human review can.
    assert reconstructed["verified_count"] == 0
    assert reconstructed["stats"]["span_count"] > 0

    memory = client.get(
        f"/api/v1/projects/{project['id']}/memory", headers=auth_headers
    ).json()
    assert memory["reconstructed"] is True
    assert memory["stats"]["claim_count"] == reconstructed["claim_count"]
    assert memory["summary"]
    assert memory["last_run"]["id"] == reconstructed["id"]

    claims = client.get(
        f"/api/v1/projects/{project['id']}/claims", headers=auth_headers
    ).json()
    assert claims["meta"]["total"] == reconstructed["claim_count"]
    assert "Verified" not in claims["status_counts"]

    for claim in claims["items"]:
        detail = client.get(
            f"/api/v1/projects/{project['id']}/claims/{claim['id']}", headers=auth_headers
        ).json()
        assert detail["evidence"], f"claim {claim['id']} has no evidence"
        for ref in detail["evidence"]:
            assert ref["span_id"], "evidence must point at a backend-owned span"
            assert ref["supporting_quote"], "evidence must carry its exact text"
            assert ref["source_name"]
        # Every verification result is stored and quotation-checked.
        for verification in detail["verifications"]:
            assert verification["verdict"] in {"supports", "partly", "none"}


def test_conflicts_and_staleness_are_detected_end_to_end(
    client, project, auth_headers, reconstructed
) -> None:
    conflicts = client.get(
        f"/api/v1/projects/{project['id']}/conflicts", headers=auth_headers
    ).json()
    kinds = {item["kind"] for item in conflicts["items"]}
    assert "value_disagreement" in kinds, conflicts["items"]
    assert "changed_over_time" in kinds, conflicts["items"]

    disagreement = next(item for item in conflicts["items"] if item["kind"] == "value_disagreement")
    assert disagreement["status"] == "open"
    assert len(disagreement["claims"]) >= 2
    values = {
        claim["text"] for claim in disagreement["claims"]
    }
    assert any("PostgreSQL 13" in text for text in values)
    assert any("PostgreSQL 15" in text for text in values)

    uncertainty = client.get(
        f"/api/v1/projects/{project['id']}/uncertainty", headers=auth_headers
    ).json()
    stale_names = {source["source_name"] for source in uncertainty["stale_sources"]}
    assert stale_names, "a superseded document must be flagged for review"
    statuses = {source["freshness"] for source in uncertainty["stale_sources"]}
    assert statuses <= {"potentially_stale", "contradicted_by_newer_evidence"}


def test_open_questions_are_recorded(client, project, auth_headers, reconstructed) -> None:
    questions = client.get(
        f"/api/v1/projects/{project['id']}/questions", headers=auth_headers
    ).json()
    assert questions["meta"]["total"] >= 1
    assert any("fraud scoring" in item["question"] for item in questions["items"])


def test_unfinished_work_is_captured(client, project, auth_headers, reconstructed) -> None:
    claims = client.get(
        f"/api/v1/projects/{project['id']}/claims",
        params={"category": "unfinished_work"},
        headers=auth_headers,
    ).json()
    assert claims["meta"]["total"] == 1
    assert "legacy invoices table" in claims["items"][0]["text"]


def test_claims_can_be_ordered_as_a_decision_timeline(
    client, project, auth_headers, reconstructed
) -> None:
    timeline = client.get(
        f"/api/v1/projects/{project['id']}/claims",
        params={"order": "timeline", "page_size": 100},
        headers=auth_headers,
    ).json()
    dates = [item["source_date"] for item in timeline["items"] if item["source_date"]]
    assert dates == sorted(dates), "the timeline must be chronological"


# ---------------------------------------------------------------------------
# Deduplication and reprocessing
# ---------------------------------------------------------------------------
def test_reprocessing_deduplicates_claims(
    client, project, auth_headers, provider, reconstructed
) -> None:
    first = client.get(
        f"/api/v1/projects/{project['id']}/claims", headers=auth_headers
    ).json()

    second_run = reconstruct(client, project["id"], provider, auth_headers)
    assert second_run.status_code == 201, second_run.text

    after = client.get(
        f"/api/v1/projects/{project['id']}/claims", headers=auth_headers
    ).json()
    assert after["meta"]["total"] == first["meta"]["total"], "claims must not be duplicated"

    detail = client.get(
        f"/api/v1/projects/{project['id']}/claims/{first['items'][0]['id']}",
        headers=auth_headers,
    ).json()
    assert any(entry["action"] == "deduped" for entry in detail["history"])


# ---------------------------------------------------------------------------
# Human review
# ---------------------------------------------------------------------------
def _first_supported_claim(client, project_id, headers) -> dict:
    listing = client.get(
        f"/api/v1/projects/{project_id}/claims",
        params={"status": "Supported", "page_size": 50},
        headers=headers,
    ).json()
    assert listing["items"], "the run must produce at least one supported claim"
    return listing["items"][0]


def test_review_is_the_only_path_to_verified(
    client, project, auth_headers, reconstructed
) -> None:
    claim = _first_supported_claim(client, project["id"], auth_headers)

    approved = client.post(
        f"/api/v1/projects/{project['id']}/claims/{claim['id']}/review",
        json={"action": "approve", "note": "Reviewed during handover."},
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "Verified"
    assert body["verified_at"]
    assert any(entry["action"] == "approved" for entry in body["history"])

    # A model re-verification must never overwrite the human decision.
    _override_provider(FakeProvider())
    try:
        reverify = client.post(
            f"/api/v1/projects/{project['id']}/claims/{claim['id']}/verify",
            headers=auth_headers,
        )
    finally:
        _clear_provider()
    assert reverify.status_code == 409


def test_review_rejection_returns_a_claim_to_uncertain(
    client, project, auth_headers, reconstructed
) -> None:
    claim = _first_supported_claim(client, project["id"], auth_headers)
    rejected = client.post(
        f"/api/v1/projects/{project['id']}/claims/{claim['id']}/review",
        json={"action": "reject", "note": "Not supported by the documentation."},
        headers=auth_headers,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "Uncertain"


def test_conflict_resolution_is_recorded(
    client, project, auth_headers, reconstructed
) -> None:
    conflict = client.get(
        f"/api/v1/projects/{project['id']}/conflicts",
        params={"kind": "value_disagreement"},
        headers=auth_headers,
    ).json()["items"][0]
    chosen = conflict["claims"][0]["id"]

    response = client.post(
        f"/api/v1/projects/{project['id']}/conflicts/{conflict['id']}/resolve",
        json={
            "action": "resolve",
            "note": "The newer commit is authoritative.",
            "chosen_claim_id": chosen,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "resolved"

    detail = client.get(
        f"/api/v1/projects/{project['id']}/claims/{chosen}", headers=auth_headers
    ).json()
    assert detail["status"] == "Supported"
    assert any(entry["action"] == "conflict_resolved" for entry in detail["history"])


# ---------------------------------------------------------------------------
# Handover
# ---------------------------------------------------------------------------
def test_handover_requires_generation_first(client, project, auth_headers) -> None:
    response = client.get(
        f"/api/v1/projects/{project['id']}/handover", headers=auth_headers
    )
    assert response.status_code == 404


def test_handover_uses_approved_claims_only(
    client, project, auth_headers, reconstructed
) -> None:
    claim = _first_supported_claim(client, project["id"], auth_headers)
    approve = client.post(
        f"/api/v1/projects/{project['id']}/claims/{claim['id']}/review",
        json={"action": "approve", "note": "Approved."},
        headers=auth_headers,
    )
    assert approve.status_code == 200, approve.text

    _override_provider(FakeProvider())
    try:
        response = client.post(
            f"/api/v1/projects/{project['id']}/handover/generate", headers=auth_headers
        )
    finally:
        _clear_provider()

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["claim_ids"] == [claim["id"]]

    statements = [
        statement
        for section in body["sections"]
        for statement in section["statements"]
    ]
    assert statements, "the handover must contain at least one linked statement"
    assert all(statement["claim_ids"] for statement in statements)

    # The deterministic validator deleted the sentence that cited no claim.
    # It survives only in the validation log, never in the handover body.
    assert any(error["code"] == "unlinked_sentence" for error in body["validation_errors"])
    assert "celebrate" not in json.dumps(body["sections"])

    latest = client.get(
        f"/api/v1/projects/{project['id']}/handover", headers=auth_headers
    ).json()
    assert latest["id"] == body["id"]


# ---------------------------------------------------------------------------
# Authentication and authorisation
# ---------------------------------------------------------------------------
MEMORY_READ_ROUTES = (
    "/memory",
    "/claims",
    "/conflicts",
    "/questions",
    "/uncertainty",
    "/processing-runs",
    "/handover",
)


@pytest.mark.parametrize("suffix", MEMORY_READ_ROUTES)
def test_memory_reads_require_authentication(client, project, suffix) -> None:
    response = client.get(f"/api/v1/projects/{project['id']}{suffix}")
    assert response.status_code == 401, response.text


def test_reconstruction_requires_authentication(client, project) -> None:
    response = client.post(
        f"/api/v1/projects/{project['id']}/memory/reconstruct", json={}
    )
    assert response.status_code == 401


def test_foreign_project_is_invisible(client, db_session, foreign_workspace, auth_headers) -> None:
    hidden = Project(workspace_id=uuid.UUID(foreign_workspace["id"]), name="Hidden")
    db_session.add(hidden)
    db_session.commit()

    for suffix in MEMORY_READ_ROUTES:
        response = client.get(f"/api/v1/projects/{hidden.id}{suffix}", headers=auth_headers)
        assert response.status_code == 404, (suffix, response.text)

    reconstruct_response = client.post(
        f"/api/v1/projects/{hidden.id}/memory/reconstruct", json={}, headers=auth_headers
    )
    assert reconstruct_response.status_code == 404


def test_unknown_claim_is_not_found(client, project, auth_headers) -> None:
    response = client.get(
        f"/api/v1/projects/{project['id']}/claims/{uuid.uuid4()}", headers=auth_headers
    )
    assert response.status_code == 404
