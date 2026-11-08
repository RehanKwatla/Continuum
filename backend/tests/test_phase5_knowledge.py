"""Phase 5 knowledge dependency and missing-knowledge tests (§6–§7).

The engines read *approved* claims plus their sourced evidence. These tests
create those rows directly through the ORM (the shape the review pipeline
produces) and exercise the HTTP layer against real PostgreSQL: a knowledge
dependency is only reported where sourced authorship exists, gaps are never
auto-filled, and a reviewer override is audited without deleting the computed
risk.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.claim import Claim
from app.models.enums import (
    ClaimStatus,
    ClaimType,
    ProcessingStatus,
    SourceType,
    WorkspaceRole,
)
from app.models.evidence import Evidence
from app.models.project import Project
from app.models.source import Source
from app.models.user import User
from app.models.workspace import WorkspaceMember

DEV_USER_EMAIL = "dev.user@example.com"


def _source(db, project_id: uuid.UUID, *, name: str, author: str) -> Source:
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


def _demote_dev_user_to_member(db, workspace_id: str) -> None:
    user = db.execute(select(User).where(User.email == DEV_USER_EMAIL)).scalar_one()
    membership = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == uuid.UUID(workspace_id),
            WorkspaceMember.user_id == user.id,
        )
    ).scalar_one()
    membership.role = WorkspaceRole.MEMBER
    db.commit()


# ---------------------------------------------------------------------------
# §7 — missing knowledge
# ---------------------------------------------------------------------------
def test_detect_gaps_before_readiness_is_404(client, project, auth_headers) -> None:
    response = client.post(
        f"/api/v1/projects/{project['id']}/knowledge-gaps/detect", headers=auth_headers
    )
    assert response.status_code == 404


def test_detect_gaps_after_readiness_returns_gaps(
    client, project, auth_headers
) -> None:
    _evaluate(client, project["id"], auth_headers)

    response = client.post(
        f"/api/v1/projects/{project['id']}/knowledge-gaps/detect", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["total"] > 0
    assert body["items"]
    first = body["items"][0]
    assert first["gap_key"]
    assert first["status"] == "Open"
    assert "decisions.documented" in {item["gap_key"] for item in body["items"]}


def test_gap_status_transitions_from_open_to_accepted_risk(
    client, project, auth_headers
) -> None:
    _evaluate(client, project["id"], auth_headers)
    detected = client.post(
        f"/api/v1/projects/{project['id']}/knowledge-gaps/detect", headers=auth_headers
    ).json()
    gap_id = detected["items"][0]["id"]

    updated = client.patch(
        f"/api/v1/projects/{project['id']}/knowledge-gaps/{gap_id}",
        json={"status": "Accepted Risk", "note": "Accepted for this release."},
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "Accepted Risk"

    accepted = client.get(
        f"/api/v1/projects/{project['id']}/knowledge-gaps",
        params={"status": "Accepted Risk"},
        headers=auth_headers,
    ).json()
    assert gap_id in {item["id"] for item in accepted["items"]}


# ---------------------------------------------------------------------------
# §6 — knowledge dependencies
# ---------------------------------------------------------------------------
def test_analyse_reports_single_person_dependency(
    client, db_session, project, auth_headers
) -> None:
    project_id = uuid.UUID(project["id"])
    source = _source(db_session, project_id, name="ownership.md", author="alice")
    _approved_claim(
        db_session,
        project_id,
        text="Alice owns the payments module.",
        claim_type=ClaimType.OWNERSHIP,
        entity="payments",
        sources=(source,),
    )
    db_session.commit()

    response = client.post(
        f"/api/v1/projects/{project['id']}/knowledge-dependencies/analyse",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["total"] >= 1
    record = next(item for item in body["items"] if item["entity"] == "payments")
    assert record["risk_status"] == "High"
    assert record["involved_people"] == ["alice"]
    assert record["dependency_level"] == 1.0


def test_list_dependencies_matches_analyse(
    client, db_session, project, auth_headers
) -> None:
    project_id = uuid.UUID(project["id"])
    source = _source(db_session, project_id, name="ownership.md", author="alice")
    _approved_claim(
        db_session,
        project_id,
        text="Alice owns the payments module.",
        claim_type=ClaimType.OWNERSHIP,
        entity="payments",
        sources=(source,),
    )
    db_session.commit()

    analysed = client.post(
        f"/api/v1/projects/{project['id']}/knowledge-dependencies/analyse",
        headers=auth_headers,
    ).json()

    listed = client.get(
        f"/api/v1/projects/{project['id']}/knowledge-dependencies", headers=auth_headers
    )
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == analysed["total"]
    assert {item["id"] for item in body["items"]} == {
        item["id"] for item in analysed["items"]
    }


def test_override_sets_effective_status_and_preserves_computed(
    client, db_session, project, auth_headers
) -> None:
    project_id = uuid.UUID(project["id"])
    source = _source(db_session, project_id, name="ownership.md", author="alice")
    _approved_claim(
        db_session,
        project_id,
        text="Alice owns the payments module.",
        claim_type=ClaimType.OWNERSHIP,
        entity="payments",
        sources=(source,),
    )
    db_session.commit()

    analysed = client.post(
        f"/api/v1/projects/{project['id']}/knowledge-dependencies/analyse",
        headers=auth_headers,
    ).json()
    dependency = next(item for item in analysed["items"] if item["entity"] == "payments")
    assert dependency["risk_status"] == "High"
    assert dependency["effective_risk_status"] == "High"

    response = client.post(
        f"/api/v1/projects/{project['id']}/knowledge-dependencies/{dependency['id']}/override",
        json={"risk_status": "Low", "note": "A backup owner is documented off-system."},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["effective_risk_status"] == "Low"
    assert body["risk_status"] == "High"
    assert body["override"]["risk_status"] == "Low"


def test_override_requires_admin_role(
    client, db_session, project, auth_headers
) -> None:
    _demote_dev_user_to_member(db_session, project["workspace_id"])

    response = client.post(
        f"/api/v1/projects/{project['id']}/knowledge-dependencies/"
        f"{uuid.uuid4()}/override",
        json={"risk_status": "Low", "note": "Trying without admin rights."},
        headers=auth_headers,
    )
    assert response.status_code == 403
