"""Phase 5 Handover Readiness Engine tests (§2–§3).

The unit tests exercise the pure catalog/scoring helpers directly. The
integration tests drive the real HTTP router against a real PostgreSQL database
and create approved claims (with evidence) through the ORM — the same shape the
review pipeline produces — so the deterministic engine is scored on real rows.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.errors import ValidationAppError
from app.models.claim import Claim
from app.models.enums import (
    ClaimStatus,
    ClaimType,
    ProcessingStatus,
    ReadinessDimension,
    SourceType,
)
from app.models.evidence import Evidence
from app.models.project import Project
from app.models.source import Source
from app.services.readiness_catalog import (
    DEFAULT_WEIGHTS,
    SCORING_FORMULA,
    band_for_score,
    default_weights,
)
from app.services.readiness_service import normalise_weights

_DIMENSION_VALUES = {dimension.value for dimension in ReadinessDimension}


# ---------------------------------------------------------------------------
# Unit: catalog + scoring helpers
# ---------------------------------------------------------------------------
def test_default_weights_totals_one_hundred() -> None:
    weights = default_weights()
    assert sum(weights.values()) == pytest.approx(100.0)
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(100.0)
    assert set(weights) == _DIMENSION_VALUES


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (95, "strong"),
        (80, "mostly_ready"),
        (60, "needs_review"),
        (10, "not_ready"),
    ],
)
def test_band_for_score(score: float, expected: str) -> None:
    assert band_for_score(score) == expected


def test_normalise_weights_none_returns_defaults() -> None:
    resolved = normalise_weights(None)
    assert {dimension.value: value for dimension, value in resolved.items()} == default_weights()


def test_normalise_weights_rejects_unknown_dimension() -> None:
    raw = default_weights()
    raw["not_a_real_dimension"] = 0.0
    with pytest.raises(ValidationAppError):
        normalise_weights(raw)


def test_normalise_weights_rejects_negative_weight() -> None:
    raw = default_weights()
    raw[ReadinessDimension.PROJECT_CONTEXT.value] = -1.0
    with pytest.raises(ValidationAppError):
        normalise_weights(raw)


def test_normalise_weights_rejects_total_not_one_hundred() -> None:
    raw = default_weights()
    raw[ReadinessDimension.PROJECT_CONTEXT.value] = raw[
        ReadinessDimension.PROJECT_CONTEXT.value
    ] + 5.0
    with pytest.raises(ValidationAppError):
        normalise_weights(raw)


def test_scoring_formula_is_a_non_empty_string() -> None:
    assert isinstance(SCORING_FORMULA, str)
    assert SCORING_FORMULA.strip()


# ---------------------------------------------------------------------------
# Helpers for integration tests
# ---------------------------------------------------------------------------
def _source(db, project_id: uuid.UUID, *, name: str = "notes.md", author: str = "alice") -> Source:
    source = Source(
        project_id=project_id,
        source_type=SourceType.UPLOADED_MARKDOWN,
        source_name=name,
        author=author,
        processing_status=ProcessingStatus.COMPLETED,
    )
    db.add(source)
    db.flush()
    return source


def _approved_claim(
    db,
    project_id: uuid.UUID,
    *,
    text: str,
    claim_type: ClaimType,
    entity: str | None = None,
    critical: bool = False,
    sources: tuple[Source, ...] = (),
) -> Claim:
    claim = Claim(
        project_id=project_id,
        text=text,
        claim_type=claim_type,
        entity=entity,
        status=ClaimStatus.VERIFIED,
        critical=critical,
        revision_number=1,
    )
    db.add(claim)
    db.flush()
    for source in sources:
        db.add(Evidence(claim_id=claim.id, source_id=source.id))
    db.flush()
    return claim


def _evaluate(client, project_id: str, headers: dict[str, str]) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/readiness/evaluate", json={}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Integration: evaluate
# ---------------------------------------------------------------------------
def test_evaluate_with_no_approved_claims_is_low_and_blocked(
    client, project, auth_headers
) -> None:
    body = _evaluate(client, project["id"], auth_headers)

    assert isinstance(body["overall_score"], float)
    assert body["overall_score"] < 30.0
    assert body["band"] in {"strong", "mostly_ready", "needs_review", "not_ready"}
    assert set(body["dimension_scores"]) == _DIMENSION_VALUES
    assert body["requirements"]
    assert body["blockers"]
    assert any(blocker["code"] == "no_approved_knowledge" for blocker in body["blockers"])
    assert isinstance(body["warnings"], list)
    assert set(body["weights"]) == _DIMENSION_VALUES
    assert body["claim_revisions"] == {}


def test_approved_claims_raise_score_and_complete_requirements(
    client, db_session, project, auth_headers
) -> None:
    before = _evaluate(client, project["id"], auth_headers)

    project_id = uuid.UUID(project["id"])
    source = _source(db_session, project_id)
    first = _approved_claim(
        db_session,
        project_id,
        text="We chose PostgreSQL because it supports JSONB well.",
        claim_type=ClaimType.DECISION,
        sources=(source,),
    )
    second = _approved_claim(
        db_session,
        project_id,
        text="We run async workers in order to scale throughput.",
        claim_type=ClaimType.DECISION,
        sources=(source,),
    )
    db_session.commit()

    after = _evaluate(client, project["id"], auth_headers)

    assert after["overall_score"] > before["overall_score"]

    completions = {item["requirement_id"]: item["completion"] for item in after["requirements"]}
    assert completions["decisions.documented"] == "Complete"
    assert "Complete" in completions.values()

    assert str(first.id) in after["claim_revisions"]
    assert str(second.id) in after["claim_revisions"]
    assert after["claim_revisions"][str(first.id)] == first.revision_number


# ---------------------------------------------------------------------------
# Integration: reads
# ---------------------------------------------------------------------------
def test_get_readiness_is_null_before_evaluation_then_latest(
    client, project, auth_headers
) -> None:
    empty = client.get(
        f"/api/v1/projects/{project['id']}/readiness", headers=auth_headers
    )
    assert empty.status_code == 200, empty.text
    overview = empty.json()
    assert overview["evaluation"] is None
    assert overview["formula"]
    assert set(overview["default_weights"]) == _DIMENSION_VALUES
    assert overview["bands"]

    evaluated = _evaluate(client, project["id"], auth_headers)
    latest = client.get(
        f"/api/v1/projects/{project['id']}/readiness", headers=auth_headers
    ).json()
    assert latest["evaluation"]["id"] == evaluated["id"]
    assert latest["evaluation"]["overall_score"] == evaluated["overall_score"]


def test_readiness_history_lists_items(client, project, auth_headers) -> None:
    first = _evaluate(client, project["id"], auth_headers)
    second = _evaluate(client, project["id"], auth_headers)

    body = client.get(
        f"/api/v1/projects/{project['id']}/readiness/history", headers=auth_headers
    ).json()
    assert body["total"] >= 2
    ids = {item["id"] for item in body["items"]}
    assert first["id"] in ids
    assert second["id"] in ids


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------
def test_non_member_gets_404_on_readiness(
    client, db_session, foreign_workspace, auth_headers
) -> None:
    foreign_project = Project(
        workspace_id=uuid.UUID(foreign_workspace["id"]), name="Someone else's project"
    )
    db_session.add(foreign_project)
    db_session.commit()

    response = client.get(
        f"/api/v1/projects/{foreign_project.id}/readiness", headers=auth_headers
    )
    assert response.status_code == 404
