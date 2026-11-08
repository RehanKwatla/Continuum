"""Health and readiness probes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import text

from app import __version__
from app.core.dependencies import AppSettings, DbSession

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
def health(settings: AppSettings) -> dict[str, Any]:
    """Cheap process check — does not touch the database."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": __version__,
        "environment": settings.environment.value,
    }


@router.get("/health/ready", summary="Readiness probe (verifies the database)")
def readiness(
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> dict[str, Any]:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # pragma: no cover - depends on the environment
        database = "unavailable"

    if database != "ok":
        response.status_code = 503

    return {
        "status": "ok" if database == "ok" else "degraded",
        "version": __version__,
        "database": database,
        # Configuration posture only — never values.
        "supabase_auth_configured": settings.supabase_auth_configured,
        "github_oauth_configured": settings.github_oauth_configured,
        "dev_auth_enabled": settings.allow_dev_auth and not settings.is_production,
    }
