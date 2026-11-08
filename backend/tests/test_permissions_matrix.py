"""Access-control matrix for the reconstruction workflow.

The workflow must load only the sources the requesting user is authorised to
use, before any content reaches a model. This is enforced by
:meth:`app.workflow.nodes.WorkflowNodes.access_filter` and checked here for every
workspace role, plus a "restricted sources never reach the prompt" assertion.
"""

from __future__ import annotations

import pytest

from app.models.enums import AccessLabel, SourceType, WorkspaceRole
from app.models.user import User
from app.workflow.nodes import _RESTRICTED_ROLES, WorkflowNodes
from app.workflow.state import STATUS_FAILED, ReconstructionState

from fake_provider import FakeProvider
from synthetic_project import create_source, create_tenant

PUBLIC_TEXT = "The billing service owns invoices."
RESTRICTED_TEXT = "The incident response key rotates weekly."


def _state(tenant) -> ReconstructionState:
    return ReconstructionState(
        project_id=tenant.project.id,
        workspace_id=tenant.workspace.id,
        requesting_user_id=tenant.user.id,
    )


def _seed(db_session, tenant) -> None:
    create_source(
        db_session,
        tenant.project.id,
        source_type=SourceType.UPLOADED_TEXT,
        source_name="public.txt",
        content=PUBLIC_TEXT,
    )
    create_source(
        db_session,
        tenant.project.id,
        source_type=SourceType.UPLOADED_TEXT,
        source_name="secret.txt",
        content=RESTRICTED_TEXT,
        access_label=AccessLabel.RESTRICTED,
    )


@pytest.mark.parametrize(
    ("role", "sees_restricted"),
    [
        (WorkspaceRole.OWNER, True),
        (WorkspaceRole.ADMIN, True),
        (WorkspaceRole.MEMBER, False),
        (WorkspaceRole.VIEWER, False),
    ],
)
def test_restricted_sources_follow_the_role_matrix(
    db_session, role: WorkspaceRole, sees_restricted: bool
) -> None:
    tenant = create_tenant(db_session, role=role)
    _seed(db_session, tenant)

    nodes = WorkflowNodes(db_session, FakeProvider())
    state = nodes.access_filter(_state(tenant))

    names = {source.source_name for source in state.source_records}
    assert "public.txt" in names
    assert ("secret.txt" in names) is sees_restricted

    if not sees_restricted:
        assert any(
            item["reason"] == "restricted_label"
            for item in state.stats["filtered_out"]
        )


def test_only_admin_and_owner_may_see_restricted_sources() -> None:
    assert set(_RESTRICTED_ROLES) == {WorkspaceRole.ADMIN, WorkspaceRole.OWNER}


def test_restricted_content_never_reaches_the_model(db_session) -> None:
    tenant = create_tenant(db_session, role=WorkspaceRole.MEMBER)
    _seed(db_session, tenant)

    provider = FakeProvider()
    nodes = WorkflowNodes(db_session, provider)
    state = nodes.access_filter(_state(tenant))
    state = nodes.prepare_source_spans(state)
    state = nodes.extract_claims(state)

    prompts = " ".join(call["prompt"] for call in provider.calls)
    assert PUBLIC_TEXT in prompts
    assert RESTRICTED_TEXT not in prompts


def test_a_non_member_is_refused_before_any_source_is_read(db_session) -> None:
    tenant = create_tenant(db_session)
    _seed(db_session, tenant)

    outsider = User(
        email="outsider@example.com", full_name="Outsider", supabase_user_id=None
    )
    db_session.add(outsider)
    db_session.flush()

    nodes = WorkflowNodes(db_session, FakeProvider())
    state = nodes.access_filter(
        ReconstructionState(
            project_id=tenant.project.id,
            workspace_id=tenant.workspace.id,
            requesting_user_id=outsider.id,
        )
    )

    assert state.workflow_status == STATUS_FAILED
    assert [error.code for error in state.processing_errors] == [
        "workspace_membership_required"
    ]
    assert state.source_records == []
