"""Typed application errors and JSON error handlers.

Every error returned by the API uses one stable envelope so the frontend can
handle failures generically::

    {"error": {"code": "not_found", "message": "...", "details": {...}}}
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("continuum.errors")


class AppError(Exception):
    """Base class for all explicitly raised API errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or {}


class AuthError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ValidationAppError(AppError):
    status_code = 422  # Unprocessable Content
    code = "validation_error"


class RateLimitError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class UpstreamError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "upstream_error"


class NotConfiguredError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "not_configured"


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        details = {**exc.details}
        if request_id:
            details["request_id"] = request_id
        headers = {"Retry-After": str(details["retry_after_seconds"])} if exc.status_code == 429 and details.get("retry_after_seconds") is not None else None
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, details),
            headers=headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            409: "conflict",
            429: "rate_limited",
        }.get(exc.status_code, "http_error")
        request_id = getattr(request.state, "request_id", None)
        details = {"request_id": request_id} if request_id else {}
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, detail, details),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        details = {"issues": _jsonable_errors(exc.errors())}
        if request_id:
            details["request_id"] = request_id
        return JSONResponse(
            status_code=422,
            content=error_body(
                "validation_error",
                "Request payload failed validation.",
                details,
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server error: %s", type(exc).__name__)
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body("internal_error", "An unexpected server error occurred.", {"request_id": request_id} if request_id else {}),
        )


def _jsonable_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for err in errors:
        cleaned.append(
            {
                "location": [str(part) for part in err.get("loc", ())],
                "message": str(err.get("msg", "")),
                "type": str(err.get("type", "")),
            }
        )
    return cleaned
