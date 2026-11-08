"""Authentication endpoints.

The backend never accepts an identity supplied by the client. Both endpoints
below derive the caller from a *verified* bearer token and, on first sight,
provision the matching local ``User`` row.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import CurrentPrincipal, CurrentUser
from app.core.security import DEV_PROVIDER
from app.schemas.auth import AuthSessionResponse, UserProfile

router = APIRouter(prefix="/auth", tags=["auth"])


def _session(principal, user) -> AuthSessionResponse:
    return AuthSessionResponse(
        user=UserProfile.model_validate(user),
        auth_provider=principal.provider,
        is_dev_session=principal.provider == DEV_PROVIDER,
    )


@router.get(
    "/me",
    response_model=AuthSessionResponse,
    summary="Return the authenticated user (provisions on first call)",
)
def read_current_user(principal: CurrentPrincipal, user: CurrentUser) -> AuthSessionResponse:
    return _session(principal, user)


@router.post(
    "/session",
    response_model=AuthSessionResponse,
    summary="Synchronise the Supabase session with the backend",
)
def sync_session(principal: CurrentPrincipal, user: CurrentUser) -> AuthSessionResponse:
    """Idempotent counterpart of ``GET /auth/me`` used right after sign-in."""
    return _session(principal, user)
