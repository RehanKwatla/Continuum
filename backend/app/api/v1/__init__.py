"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    dashboard,
    github,
    handover,
    health,
    memory,
    projects,
    sources,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(projects.router)
api_router.include_router(dashboard.router)
api_router.include_router(sources.router)
api_router.include_router(github.router)
api_router.include_router(memory.router)
api_router.include_router(handover.router)

__all__ = ["api_router"]
