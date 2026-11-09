"""Public demo endpoints (frictionless judge access).

This router is the *explicit* public-demo access policy demanded by the
brief:

* it exposes exactly one synthetic workspace and nothing else — the identifier
  it returns is the id of the seeded ``Continuum Demo Workspace``. Every other
  API route keeps working unchanged for a token-less visitor because the demo
  principal is a genuine *member of that workspace only*, so the existing
  membership checks continue to hide all real tenants;
* it is read-only by default (``public_demo_write_guard``), with a single
  allowlisted, isolated demonstration action: resetting the disposable demo
  data to a pristine seed;
* it never returns secrets, tokens, environment values or other users' data.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.dependencies import DbSession, public_demo_write_guard
from app.core.errors import NotFoundError
from app.demo import (
    DEMO_BANNER_LABEL,
    DEMO_DATA_DISCLAIMER,
    DemoSeedResult,
    ensure_demo_data,
    reset_demo_data,
)

router = APIRouter(
    prefix="/public/demo",
    tags=["public-demo"],
    # Applied to every endpoint here: token-less visitors may read only, plus
    # the single allowlisted reset action (see PUBLIC_DEMO_WRITE_ALLOWLIST).
    dependencies=[Depends(public_demo_write_guard)],
)


class PublicDemoStatus(BaseModel):
    """Everything the frontend needs to open the demo without a login step."""

    enabled: bool = Field(description="Whether public demo mode is active on this deployment.")
    read_only: bool = Field(description="Whether writes are disabled for token-less visitors.")
    seeded: bool = Field(description="Whether the synthetic demo data is present.")
    banner_label: str
    disclaimer: str
    workspace_id: uuid.UUID | None = None
    workspace_name: str | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    links: dict[str, str] = Field(default_factory=dict)
    projects: list[dict[str, str | uuid.UUID]] = Field(default_factory=list)


def _status(result: DemoSeedResult, *, enabled: bool, read_only: bool) -> PublicDemoStatus:
    project_id = result.project_id
    return PublicDemoStatus(
        enabled=enabled,
        read_only=read_only,
        seeded=True,
        banner_label=DEMO_BANNER_LABEL,
        disclaimer=DEMO_DATA_DISCLAIMER,
        workspace_id=result.workspace_id,
        workspace_name=result.workspace_name,
        project_id=project_id,
        project_name=result.project_name,
        counts=result.counts,
        projects=result.projects,
        # Relative to the versioned API prefix; the frontend resolves the host.
        links={
            "project": f"/projects/{project_id}",
            "sources": f"/projects/{project_id}/sources",
            "memory": f"/projects/{project_id}/memory",
            "review": f"/projects/{project_id}/review",
            "conflicts": f"/projects/{project_id}/conflicts",
            "handover": f"/projects/{project_id}/handover",
            "readiness": f"/projects/{project_id}/readiness",
        },
    )


@router.get(
    "",
    response_model=PublicDemoStatus,
    summary="Public demo status and demo workspace identifiers",
)
def read_public_demo(db: DbSession) -> PublicDemoStatus:
    """Return the demo workspace/project so a judge lands inside the product.

    Idempotently seeds the synthetic workspace on first call, so a fresh
    deployment is immediately explorable. No credential is required.
    """
    settings = get_settings()
    if not settings.public_demo_mode:
        raise NotFoundError(
            "Public demo mode is not enabled on this deployment.",
            code="public_demo_disabled",
        )

    result = ensure_demo_data(db)
    db.commit()
    return _status(result, enabled=True, read_only=settings.public_demo_read_only)


@router.post(
    "/reset",
    response_model=PublicDemoStatus,
    summary="Reset the disposable demo workspace to a pristine seed",
)
def reset_public_demo(db: DbSession) -> PublicDemoStatus:
    """Purge and rebuild the synthetic workspace.

    This is the *only* write token-less visitors may perform (see
    ``PUBLIC_DEMO_WRITE_ALLOWLIST``). It touches nothing but the disposable
    demo workspace, so a judge can always restore a known-good demonstration.
    """
    settings = get_settings()
    if not settings.public_demo_mode:
        raise NotFoundError(
            "Public demo mode is not enabled on this deployment.",
            code="public_demo_disabled",
        )
    result = reset_demo_data(db)
    db.commit()
    return _status(result, enabled=True, read_only=settings.public_demo_read_only)


__all__: list[str] = ["router"]
