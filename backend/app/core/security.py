"""Authentication primitives.

The backend NEVER trusts user/workspace identifiers supplied by the frontend.
Identity always comes from a verified JWT (Supabase) or, in development only,
a static local token guarded by configuration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import settings
from app.core.errors import AuthError

logger = logging.getLogger("continuum.security")

DEV_PROVIDER = "dev"
SUPABASE_PROVIDER = "supabase"
DEMO_PROVIDER = "demo"

#: Fixed identity used for token-less requests when public demo mode is on.
#: It carries no real personal information and belongs only to the synthetic
#: demo workspace. The reserved ``example.com`` domain keeps it unmistakably
#: non-routable.
DEMO_SUBJECT = "public-demo-user"
DEMO_EMAIL = "public-demo@example.com"


@dataclass(frozen=True)
class AuthPrincipal:
    """Identity extracted from a verified credential."""

    subject: str
    provider: str
    email: str | None = None
    full_name: str | None = None
    claims: dict[str, Any] = field(default_factory=dict)


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)


def _decode_supabase_token(token: str) -> dict[str, Any]:
    if not settings.supabase_url and not settings.supabase_jwt_secret:
        raise AuthError(
            "Supabase authentication is not configured on the server.",
            code="auth_not_configured",
            status_code=503,
        )

    options = {"verify_aud": bool(settings.supabase_jwt_audience)}
    audience = settings.supabase_jwt_audience or None

    try:
        if settings.supabase_jwt_secret:
            # Symmetric (HS256) projects.
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256", "HS384", "HS512"],
                audience=audience,
                options=options,
            )

        # Asymmetric projects: verify against the project JWKS endpoint.
        jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256", "EdDSA"],
            audience=audience,
            options=options,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Access token has expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Access token is invalid.", code="invalid_token") from exc


def principal_from_token(token: str) -> AuthPrincipal:
    """Resolve a bearer token into an :class:`AuthPrincipal`."""
    token = (token or "").strip()
    if not token:
        raise AuthError("Missing bearer token.")

    if settings.allow_dev_auth and not settings.is_production and token == settings.dev_auth_token:
        return AuthPrincipal(
            subject="dev-user",
            provider=DEV_PROVIDER,
            email="dev.user@example.com",
            full_name="Development User",
            claims={"dev": True},
        )

    claims = _decode_supabase_token(token)
    subject = claims.get("sub")
    if not subject:
        raise AuthError("Token is missing the 'sub' claim.", code="invalid_token")

    metadata = claims.get("user_metadata") or {}
    full_name = metadata.get("full_name") or metadata.get("name")
    return AuthPrincipal(
        subject=str(subject),
        provider=SUPABASE_PROVIDER,
        email=claims.get("email"),
        full_name=full_name,
        claims=claims,
    )


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthError("Authorization header is required.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("Authorization header must use the Bearer scheme.")
    return token.strip()


def demo_principal() -> AuthPrincipal:
    """The read-only identity served to token-less requests in public demo mode.

    This is NOT an authentication bypass for real data: the identity is a
    member of the single synthetic demo workspace and of nothing else, so every
    membership check still hides other tenants' resources.
    """
    return AuthPrincipal(
        subject=DEMO_SUBJECT,
        provider=DEMO_PROVIDER,
        email=DEMO_EMAIL,
        full_name="Public Demo",
        claims={"public_demo": True},
    )
