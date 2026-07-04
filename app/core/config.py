"""Application configuration.

Pydantic-settings v2 reads configuration from (in priority order):
    1. Arguments passed to ``Settings(...)``
    2. **Process environment variables** (e.g. ``DATABASE_URL`` set in the shell)
    3. The ``.env`` file at the project root
    4. Field defaults

That precedence is the source of a very common footgun: if ``DATABASE_URL`` is
exported in the user's shell or set as a Windows system environment variable,
it silently overrides whatever is in ``.env``. Editing ``.env`` then appears to
"have no effect", which is the exact symptom of the alembic ``InvalidPasswordError``
we debugged here.

To make the active source explicit, :func:`get_settings` records whether the
``DATABASE_URL`` came from the process environment or from ``.env`` and exposes
it via :attr:`Settings.database_url_source`. The alembic ``env.py`` prints this
on startup so you always know what is actually being used.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root is two levels up from app/core/config.py
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ENV_FILE = os.path.join(_PROJECT_ROOT, ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Multi-Cloud AI Cost Detective"
    app_env: Literal["local", "development", "staging", "production"] = "local"
    app_version: str = "0.1.0"
    app_debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    database_url: str = Field(
        default="postgresql+asyncpg://mcaicd:mcaicd@localhost:5432/mcaicd",
        validation_alias="DATABASE_URL",
    )
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=20, ge=0)
    db_pool_timeout: int = Field(default=30, ge=1)
    db_pool_recycle: int = Field(default=1800, ge=30)

    cors_origins: list[AnyUrl] = []

    # --- Authentication / JWT ---
    jwt_secret_key: str = Field(
        default="change-me-in-production",
        validation_alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        validation_alias="JWT_ALGORITHM",
    )
    access_token_expire_minutes: int = Field(
        default=30,
        ge=1,
        validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    refresh_token_expire_days: int = Field(
        default=7,
        ge=1,
        validation_alias="REFRESH_TOKEN_EXPIRE_DAYS",
    )
    # Placeholder: rate limiting will be enforced in Sprint 0.3+ / middleware layer.
    auth_rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        validation_alias="AUTH_RATE_LIMIT_PER_MINUTE",
    )
    # Placeholder: account lockout after N failed attempts.
    auth_max_login_attempts: int = Field(
        default=5,
        ge=1,
        validation_alias="AUTH_MAX_LOGIN_ATTEMPTS",
    )

    # --- AWS Cost Explorer ---
    aws_default_region: str = Field(
        default="us-east-1",
        validation_alias="AWS_DEFAULT_REGION",
    )
    aws_profile: str | None = Field(
        default=None,
        validation_alias="AWS_PROFILE",
    )
    aws_access_key_id: str | None = Field(
        default=None,
        validation_alias="AWS_ACCESS_KEY_ID",
    )
    aws_secret_access_key: str | None = Field(
        default=None,
        validation_alias="AWS_SECRET_ACCESS_KEY",
    )
    aws_cost_explorer_enabled: bool = Field(
        default=True,
        validation_alias="AWS_COST_EXPLORER_ENABLED",
    )

    @computed_field
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @computed_field
    @property
    def database_url_source(self) -> str:
        """Report which source actually supplied ``database_url``.

        Returns one of:
            ``"process env"`` — a ``DATABASE_URL`` env var is set in the shell
            ``".env file"``   — value came from the project ``.env`` file
            ``"default"``     — neither was set; the pydantic default was used
        """
        if "DATABASE_URL" in os.environ:
            return "process env"
        if os.path.isfile(_ENV_FILE):
            with open(_ENV_FILE, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip().startswith("DATABASE_URL"):
                        return ".env file"
        return "default"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
