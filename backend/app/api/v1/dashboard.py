"""Dashboard aggregate endpoint — real database numbers, never mocked."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.schemas.dashboard import DashboardStats
from app.services.project_service import ProjectService

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardStats, summary="Workspace dashboard totals")
def read_dashboard(user: CurrentUser, db: DbSession) -> DashboardStats:
    return ProjectService(db).dashboard(user)
