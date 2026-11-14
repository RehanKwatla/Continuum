"""Continuum API application factory.

Phase 1 (foundation), Phase 2 (source ingestion), Phase 3 (AI reconstruction),
Phase 4 (review, approval and handover) and Phase 5 (readiness, successor
experience, knowledge risk and evaluation) are wired here.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
import hashlib
from collections import deque
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

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

#: Request id header echoed back to the caller for log correlation.
REQUEST_ID_HEADER = "X-Request-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation id to every request and log one structured line.

    The id is taken from the inbound ``X-Request-ID`` when present (so a proxy or
    a frontend can supply one) and generated otherwise, then echoed on the
    response so a failure can be traced from the UI to the server log.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "request_id=%s method=%s path=%s status=500 duration_ms=%s",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
            )
            raise
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add conservative security headers to every response.

    Static, safe defaults that never leak information and do not interfere with
    the JSON API or the generated OpenAPI docs.
    """

    _HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Resource-Policy": "same-site",
        "X-Permitted-Cross-Domain-Policies": "none",
        # Content-Security-Policy: lock down the API to JSON-only responses and
        # block any inline/script execution in the browser.
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none';",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    }

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response = await call_next(request)
        for key, value in self._HEADERS.items():
            response.headers.setdefault(key, value)
        return response


class PublicRateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client request budget for *token-less* (public demo) traffic.

    Only anonymous requests are counted: requests that carry an ``Authorization``
    header are governed by their own identity and are never throttled here. CORS
    preflight (``OPTIONS``) is exempt so the browser's own handshake is not
    affected.
    """

    #: Upper bound on tracked clients, so a flood of distinct IPs cannot grow
    #: the table without limit.
    _MAX_CLIENTS = 10_000

    def __init__(self, app, *, limit: int, window_seconds: int = 60) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.limit = max(1, limit)
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _client_key(self, request: Request) -> str:
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if (
            not settings.public_demo_mode
            or request.method == "OPTIONS"
            or request.headers.get("authorization")
        ):
            return await call_next(request)

        now = time.monotonic()
        key = self._client_key(request)
        with self._lock:
            bucket = self._hits.get(key)
            if bucket is None:
                if len(self._hits) >= self._MAX_CLIENTS:
                    self._hits.clear()
                bucket = deque()
                self._hits[key] = bucket
            while bucket and now - bucket[0] >= self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.limit:
                retry_after = int(self.window_seconds - (now - bucket[0])) + 1
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limited",
                            "message": (
                                "Too many requests to the public demo. "
                                "Please slow down and try again shortly."
                            ),
                            "details": {"retry_after_seconds": retry_after, "request_id": getattr(request.state, "request_id", None)},
                        }
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client request budget for *authenticated* traffic.

    Applies to every request that carries an ``Authorization`` header.
    Uses the authenticated subject (or the client IP as fallback) as the key so
    a single abusive client cannot exhaust the shared pool.
    """

    _MAX_CLIENTS = 10_000

    def __init__(self, app, *, limit: int, window_seconds: int = 60) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.limit = max(1, limit)
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _client_key(self, request: Request) -> str:
        auth = request.headers.get("authorization")
        if auth:
            scheme, _, token = auth.partition(" ")
            if scheme.lower() == "bearer" and token.strip():
                return f"auth:{hashlib.sha256(token.strip().encode()).hexdigest()[:16]}"
        if request.client and request.client.host:
            return f"ip:{request.client.host}"
        return "ip:unknown"

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if request.method == "OPTIONS":
            return await call_next(request)
        if not request.headers.get("authorization"):
            return await call_next(request)

        now = time.monotonic()
        key = self._client_key(request)
        with self._lock:
            bucket = self._hits.get(key)
            if bucket is None:
                if len(self._hits) >= self._MAX_CLIENTS:
                    self._hits.clear()
                bucket = deque()
                self._hits[key] = bucket
            while bucket and now - bucket[0] >= self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.limit:
                retry_after = int(self.window_seconds - (now - bucket[0])) + 1
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limited",
                            "message": (
                                "Too many requests. Please slow down and try again shortly."
                            ),
                            "details": {"retry_after_seconds": retry_after, "request_id": getattr(request.state, "request_id", None)},
                        }
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)
        return await call_next(request)


class MaxRequestSizeMiddleware(BaseHTTPMiddleware):
    """Reject requests whose body exceeds the configured limit.

    Reads ``Content-Length`` before the body is consumed so oversized requests
    are refused early without allocating memory.
    """

    def __init__(self, app, *, max_bytes: int) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                size = int(content_length)
            except ValueError:
                size = 0
            if size > self.max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "request_entity_too_large",
                            "message": "Request body exceeds the allowed size limit.",
                            "details": {"max_request_size_bytes": self.max_bytes},
                        }
                    },
                )
        return await call_next(request)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "Starting %s v%s (env=%s, supabase=%s, github=%s, dev_auth=%s, public_demo=%s)",
        settings.app_name,
        __version__,
        settings.environment.value,
        "on" if settings.supabase_auth_configured else "off",
        "on" if settings.github_oauth_configured else "off",
        "on" if (settings.allow_dev_auth and not settings.is_production) else "off",
        "on" if settings.public_demo_mode else "off",
    )
    if settings.public_demo_mode:
        _seed_public_demo()
    yield
    logger.info("Shutting down %s", settings.app_name)


def _seed_public_demo() -> None:
    """Idempotently materialise the synthetic demo workspace at startup.

    A failure here is logged but never prevents the API from starting — the
    ``/public/demo`` endpoint seeds lazily as a fallback.
    """
    # Imported lazily so a deployment that does not use demo mode never pays for
    # (or accidentally triggers) the seeding code path.
    from app.db.session import session_scope
    from app.demo import ensure_demo_data

    try:
        with session_scope() as db:
            result = ensure_demo_data(db)
        logger.info(
            "Public demo workspace ready (workspace=%s, project=%s, counts=%s)",
            result.workspace_name,
            result.project_name,
            result.counts,
        )
    except Exception:  # pragma: no cover - depends on the environment
        logger.exception("Failed to seed the public demo workspace; will retry on demand.")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Agentic Project Continuity Platform — reconstruct project knowledge "
            "from authorised sources, verify it, review it, and hand it over with a "
            "deterministic readiness assessment."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Order note: ``add_middleware`` prepends, so the *last* added middleware is
    # the outermost. CORS is added last so that responses produced by the other
    # middleware (e.g. a 429 from the rate limiter) still carry CORS headers and
    # are readable by the browser.
    app.add_middleware(MaxRequestSizeMiddleware, max_bytes=settings.max_request_size_bytes)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        PublicRateLimitMiddleware,
        limit=settings.public_demo_rate_limit_per_minute,
    )
    app.add_middleware(
        RateLimitMiddleware,
        limit=settings.api_rate_limit_per_minute,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"^https://.*\.vercel\.app$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
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
