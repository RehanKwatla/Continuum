"""Phase 5 successor task checklist tests (§5).

The checklist is *derived from approved knowledge*, so these integration tests
create approved claims through the ORM (the same shape the review pipeline
produces) and drive the real HTTP router against PostgreSQL. Nothing invents an
owner or a deadline: the assertions below check exactly that.
"""

from __future__ import annotations

import uuid

from app.models.claim import Claim
from app.models.enums import ClaimStatus, ClaimType
from app.models.project import Project


def _approved_claim(
    db,
    project_id: uuid.UUID,
    *,
    text: str,
    claim_type: ClaimType,
    entity: str | None = None,
) -> Claim:
    claim = Claim(
        project_id=project_id,
        text=text,
        claim_type=claim_type,
        entity=entity,
        status=ClaimStatus.VERIFIED,
        revision_number=1,
    )
    db.add(claim)
    db.flush()
    return claim


def _derive(client, project_id: str, headers: dict[str, str]) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/successor-tasks/derive", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def _tasks(client, project_id: str, headers: dict[str, str]) -> dict:
    response = client.get(
        f"/api/v1/projects/{project_id}/successor-tasks", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_derive_is_idempotent(client, db_session, project, auth_headers) -> None:
    project_id = uuid.UUID(project["id"])
    _approved_claim(
        db_session,
        project_id,
        text="Finish the invoices migration.",
        claim_type=ClaimType.TASK,
        entity="invoices",
    )
    _approved_claim(
        db_session,
        project_id,
        text="The old billing queue still needs decommissioning.",
        claim_type=ClaimType.UNFINISHED_WORK,
        entity="billing",
    )
    db_session.commit()

    first = _derive(client, project["id"], auth_headers)
    assert first["created"] == 2
    assert first["total"] == 2
    assert len(first["task_ids"]) == 2

    listed = _tasks(client, project["id"], auth_headers)
    assert listed["total"] == 2
    assert all(item["origin"] == "derived" for item in listed["items"])

    second = _derive(client, project["id"], auth_headers)
    assert second["created"] == 0
    assert second["total"] == 2
    assert second["task_ids"] == []


def test_owner_only_set_when_ownership_claim_covers_same_entity(
    client, db_session, project, auth_headers
) -> None:
    project_id = uuid.UUID(project["id"])
    _approved_claim(
        db_session,
        project_id,
        text="Reduce payments technical debt.",
        claim_type=ClaimType.TASK,
        entity="payments",
    )
    _approved_claim(
        db_session,
        project_id,
        text="Fix billing rounding errors.",
        claim_type=ClaimType.TASK,
        entity="billing",
    )
    ownership_text = "Alice owns the payments module."
    _approved_claim(
        db_session,
        project_id,
        text=ownership_text,
        claim_type=ClaimType.OWNERSHIP,
        entity="payments",
    )
    db_session.commit()

    _derive(client, project["id"], auth_headers)
    listed = _tasks(client, project["id"], auth_headers)
    by_title = {item["title"]: item for item in listed["items"]}

    assert by_title["Reduce payments technical debt."]["owner"] == ownership_text
    assert by_title["Fix billing rounding errors."]["owner"] is None


def test_manual_task_has_manual_origin_and_no_owner(
    client, project, auth_headers
) -> None:
    response = client.post(
        f"/api/v1/projects/{project['id']}/successor-tasks",
        json={"title": "Write the incident runbook."},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    task = response.json()

    assert task["origin"] == "manual"
    assert task["owner"] is None
    assert task["status"] == "Not Started"
    assert task["origin_claim_id"] is None

    listed = _tasks(client, project["id"], auth_headers)
    assert task["id"] in {item["id"] for item in listed["items"]}


def test_status_update_is_recorded_in_audit_trail(
    client, project, auth_headers
) -> None:
    created = client.post(
        f"/api/v1/projects/{project['id']}/successor-tasks",
        json={"title": "Review the deployment procedure."},
        headers=auth_headers,
    ).json()

    updated = client.patch(
        f"/api/v1/projects/{project['id']}/successor-tasks/{created['id']}",
        json={"status": "In Progress", "note": "Started today."},
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "In Progress"

    trail = client.get(
        f"/api/v1/projects/{project['id']}/audit",
        params={"action": "successor_task_status_changed"},
        headers=auth_headers,
    )
    assert trail.status_code == 200, trail.text
    items = trail.json()["items"]
    assert items
    entry = next(
        item for item in items if item["metadata"].get("to") == "In Progress"
    )
    assert entry["metadata"]["from"] == "Not Started"
    assert entry["resource_id"] == created["id"]


def test_non_member_gets_404_on_successor_tasks(
    client, db_session, foreign_workspace, auth_headers
) -> None:
    foreign_project = Project(
        workspace_id=uuid.UUID(foreign_workspace["id"]), name="Someone else's project"
    )
    db_session.add(foreign_project)
    db_session.commit()

    response = client.get(
        f"/api/v1/projects/{foreign_project.id}/successor-tasks", headers=auth_headers
    )
    assert response.status_code == 404
