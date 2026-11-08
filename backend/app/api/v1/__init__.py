"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1 import (
    auth,
    dashboard,
    github,
    handover,
    health,
    memory,
    projects,
    public_demo,
    readiness,
    sources,
    workspaces,
)
from app.core.dependencies import public_demo_write_guard

# The public-demo access policy is applied to *every* versioned API route: a
# token-less visitor may read freely but may not mutate, apart from the single
# allowlisted demo-reset action. Requests carrying a real credential are
# unaffected (see ``public_demo_write_guard``).
api_router = APIRouter(dependencies=[Depends(public_demo_write_guard)])
api_router.include_router(health.router)
api_router.include_router(public_demo.router)
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(projects.router)
api_router.include_router(dashboard.router)
api_router.include_router(sources.router)
api_router.include_router(github.router)
api_router.include_router(memory.router)
api_router.include_router(handover.router)
api_router.include_router(readiness.router)
api_router.include_router(readiness.workspace_router)

__all__ = ["api_router"]
