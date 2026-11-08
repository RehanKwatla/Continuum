"""Application configuration.

All credentials are read from environment variables (see ``.env.example``).
Nothing is hard-coded and no secret is ever logged.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import field_validator
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

    # --- GitHub OAuth --------------------------------------------------------
    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_oauth_redirect_uri: str = "http://localhost:8000/api/v1/github/callback"
    github_oauth_frontend_redirect: str = "http://localhost:5173/sources"
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

    # --- AI (Phase 3 contract only) -----------------------------------------
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

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
            self.github_client_id
            and self.github_client_secret
            and self.github_token_encryption_key
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
