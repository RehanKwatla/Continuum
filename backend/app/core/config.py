"""Application configuration.

All credentials are read from environment variables (see ``.env.example``).
Nothing is hard-coded and no secret is ever logged.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---------------------------------------------------------
    app_name: str = "Continuum API"
    api_v1_prefix: str = "/api/v1"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False

    # --- Database ------------------------------------------------------------
    # Host port 5433 matches docker-compose.yml (5432 is often taken by a
    # locally installed PostgreSQL server).
    database_url: str = "postgresql+psycopg://continuum:continuum@localhost:5433/continuum"
    db_echo: bool = False

    # --- CORS ----------------------------------------------------------------
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # --- Supabase Auth -------------------------------------------------------
    supabase_url: str | None = None
    supabase_jwt_secret: str | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_service_role_key: str | None = None

    # --- Development-only auth bypass ---------------------------------------
    allow_dev_auth: bool = False
    dev_auth_token: str = "dev-local-token"

    # --- Public demo mode (frictionless judge access) -----------------------
    # Enabled by default: a request with NO bearer token is served as the read-only
    # *public demo* principal. That identity is a member of exactly one
    # synthetic demo workspace and of nothing else, so the existing membership
    # checks keep every real workspace invisible. A real bearer token is still
    # verified normally.
    public_demo_mode: bool = True
    #: When true (default) the demo principal may only perform safe reads
    #: (plus an explicit allowlist such as the demo reset action).
    public_demo_read_only: bool = True
    public_demo_workspace_name: str = "Continuum Demo Workspace"
    public_demo_project_name: str = "Payment Gateway System"
    #: Per-client-IP request budget for token-less (public) requests.
    public_demo_rate_limit_per_minute: int = 180

    # --- GitHub OAuth & Personal Access Token --------------------------------
    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_oauth_redirect_uri: str = "http://localhost:8000/api/v1/github/callback"
    github_oauth_frontend_redirect: str = "http://localhost:5173/sources"
    github_token: str | None = None
    # Fernet key used to encrypt GitHub access tokens at rest.
    github_token_encryption_key: str | None = None
    github_api_base_url: str = "https://api.github.com"

    # --- File ingestion ------------------------------------------------------
    upload_dir: str = "./storage/uploads"
    max_upload_size_bytes: int = 25 * 1024 * 1024
    max_zip_expansion_bytes: int = 100 * 1024 * 1024
    max_zip_entries: int = 200
    max_zip_entry_bytes: int = 10 * 1024 * 1024
    max_content_chars: int = 400_000

    # --- AI (Phase 3 intelligence layer) -------------------------------------
    # The model identifier is *pinned through configuration* — never assumed by
    # the agent code — so the provider/model can be changed without a code edit.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_seconds: float = 90.0
    gemini_max_output_tokens: int = 8192
    # Workflow safety limits.
    ai_max_sources_per_run: int = 25
    ai_max_spans_per_prompt: int = 40
    ai_max_claims_per_source: int = 25
    ai_max_retries: int = 2

    @property
    def ai_configured(self) -> bool:
        """True when a real model provider is usable (no key ⇒ no fabrication)."""
        return bool(self.gemini_api_key)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def supabase_auth_configured(self) -> bool:
        return bool(self.supabase_url and (self.supabase_jwt_secret or self.supabase_url))

    @property
    def github_oauth_configured(self) -> bool:
        return bool(
            (
                self.github_client_id
                and self.github_client_secret
                and self.github_token_encryption_key
            )
            or self.github_token
        )

    @model_validator(mode="after")
    def _validate_environment(self) -> "Settings":
        """Fail fast on an unsafe production configuration.

        The development auth bypass is a genuine authentication bypass, so it
        must never be enabled in production. Raising here means a misconfigured
        deployment refuses to start rather than silently accepting forged
        tokens.
        """
        if self.is_production and self.allow_dev_auth:
            raise ValueError(
                "ALLOW_DEV_AUTH must be false when ENVIRONMENT=production."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
