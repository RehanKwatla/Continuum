"""Continuum API application factory.

Phase 1 (foundation) + Phase 2 (source ingestion) are wired here. Phase 3 AI
agents are *not* implemented — only their typed contracts exist.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.api.v1.health import router as health_router
from app.core.config import settings
from app.core.errors import register_exception_handlers

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("continuum")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "Starting %s v%s (env=%s, supabase=%s, github=%s, dev_auth=%s)",
        settings.app_name,
        __version__,
        settings.environment.value,
        "on" if settings.supabase_auth_configured else "off",
        "on" if settings.github_oauth_configured else "off",
        "on" if (settings.allow_dev_auth and not settings.is_production) else "off",
    )
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Agentic Project Continuity Platform — reconstruct project knowledge "
            "from authorised sources. Phase 1 foundation + Phase 2 ingestion."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # Root-level probes (conventional) plus the versioned API surface.
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    def index() -> dict[str, Any]:
        return {
            "service": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "api": settings.api_v1_prefix,
            "tagline": "People may leave. The knowledge shouldn't have to.",
        }

    return app


app = create_app()
