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
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root is two levels up from app/core/config.py
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
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
    # Reserved for future account lockout logic after N failed attempts.
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
    aws_session_token: str | None = Field(
        default=None,
        validation_alias="AWS_SESSION_TOKEN",
    )
    aws_cost_explorer_enabled: bool = Field(
        default=True,
        validation_alias="AWS_COST_EXPLORER_ENABLED",
    )
    aws_use_mock_data: bool = Field(
        default=False,
        validation_alias="AWS_USE_MOCK_DATA",
        description="Use deterministic local AWS data instead of Cost Explorer.",
    )

    # --- Azure Cost Management ---
    azure_cost_management_enabled: bool = Field(
        default=True,
        validation_alias="AZURE_COST_MANAGEMENT_ENABLED",
    )
    azure_subscription_id: str | None = Field(
        default=None,
        validation_alias="AZURE_SUBSCRIPTION_ID",
    )
    azure_tenant_id: str | None = Field(
        default=None,
        validation_alias="AZURE_TENANT_ID",
    )
    azure_client_id: str | None = Field(
        default=None,
        validation_alias="AZURE_CLIENT_ID",
    )
    azure_client_secret: str | None = Field(
        default=None,
        validation_alias="AZURE_CLIENT_SECRET",
    )
    azure_request_timeout: int | None = Field(
        default=30,
        ge=1,
        validation_alias="AZURE_REQUEST_TIMEOUT",
    )

    # --- GCP Billing ---
    gcp_billing_enabled: bool = Field(
        default=True,
        validation_alias="GCP_BILLING_ENABLED",
    )
    google_application_credentials: str | None = Field(
        default=None,
        validation_alias="GOOGLE_APPLICATION_CREDENTIALS",
    )
    gcp_billing_account: str | None = Field(
        default=None,
        validation_alias="GCP_BILLING_ACCOUNT",
    )
    gcp_billing_project: str | None = Field(
        default=None,
        validation_alias="GCP_BILLING_PROJECT",
    )
    gcp_billing_dataset: str | None = Field(
        default=None,
        validation_alias="GCP_BILLING_DATASET",
    )
    gcp_billing_table: str | None = Field(
        default=None,
        validation_alias="GCP_BILLING_TABLE",
    )

    # --- Shared infrastructure ---
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="REDIS_URL",
    )
    cache_ttl_seconds: int = Field(
        default=300,
        ge=1,
        validation_alias="CACHE_TTL_SECONDS",
    )
    rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        validation_alias="RATE_LIMIT_PER_MINUTE",
    )

    # --- Gemini cost insights (Sprint 1.5) ---
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias="GEMINI_API_KEY",
    )
    ai_insight_enabled: bool = Field(
        default=False,
        validation_alias="AI_INSIGHT_ENABLED",
    )
    ai_insight_model: str = Field(
        default="gemini-2.0-flash",
        validation_alias="AI_INSIGHT_MODEL",
    )
    ai_insight_max_output_tokens: int = Field(
        default=512,
        ge=64,
        le=2048,
        validation_alias="AI_INSIGHT_MAX_OUTPUT_TOKENS",
    )
    ai_insight_timeout_seconds: int = Field(
        default=12,
        ge=1,
        le=60,
        validation_alias="AI_INSIGHT_TIMEOUT_SECONDS",
    )
    ai_insight_percentage_threshold: Decimal = Field(
        default=Decimal("10.00"),
        ge=0,
        validation_alias="AI_INSIGHT_PERCENTAGE_THRESHOLD",
    )
    ai_insight_absolute_threshold: Decimal = Field(
        default=Decimal("50.00"),
        ge=0,
        validation_alias="AI_INSIGHT_ABSOLUTE_THRESHOLD",
    )
    ai_insight_max_events: int = Field(
        default=3,
        ge=1,
        le=10,
        validation_alias="AI_INSIGHT_MAX_EVENTS",
    )
    ai_insight_cache_ttl_seconds: int = Field(
        default=3600,
        ge=1,
        validation_alias="AI_INSIGHT_CACHE_TTL_SECONDS",
    )

    # --- Deterministic anomaly detection (Sprint 1.7) ---
    anomaly_lookback_days: int = Field(
        default=30, ge=7, le=365, validation_alias="ANOMALY_LOOKBACK_DAYS"
    )
    anomaly_min_history_points: int = Field(
        default=7, ge=3, le=365, validation_alias="ANOMALY_MIN_HISTORY_POINTS"
    )
    anomaly_min_cost: Decimal = Field(
        default=Decimal("1.00"), ge=0, validation_alias="ANOMALY_MIN_COST"
    )
    anomaly_min_deviation_percentage: Decimal = Field(
        default=Decimal("20.00"),
        ge=0,
        validation_alias="ANOMALY_MIN_DEVIATION_PERCENTAGE",
    )
    anomaly_low_score: Decimal = Field(
        default=Decimal("2.00"), ge=0, validation_alias="ANOMALY_LOW_SCORE"
    )
    anomaly_medium_score: Decimal = Field(
        default=Decimal("3.00"), ge=0, validation_alias="ANOMALY_MEDIUM_SCORE"
    )
    anomaly_high_score: Decimal = Field(
        default=Decimal("4.00"), ge=0, validation_alias="ANOMALY_HIGH_SCORE"
    )
    anomaly_critical_score: Decimal = Field(
        default=Decimal("6.00"), ge=0, validation_alias="ANOMALY_CRITICAL_SCORE"
    )
    anomaly_cache_ttl_seconds: int = Field(
        default=900, ge=1, validation_alias="ANOMALY_CACHE_TTL_SECONDS"
    )

    # --- Cost alerts and email notifications (Sprint 2.2) ---
    alerts_scheduler_enabled: bool = Field(
        default=False, validation_alias="ALERTS_SCHEDULER_ENABLED"
    )
    alerts_evaluation_interval_seconds: int = Field(
        default=900, ge=60, validation_alias="ALERTS_EVALUATION_INTERVAL_SECONDS"
    )
    alert_email_enabled: bool = Field(
        default=False, validation_alias="ALERT_EMAIL_ENABLED"
    )
    alert_smtp_host: str | None = Field(default=None, validation_alias="ALERT_SMTP_HOST")
    alert_smtp_port: int = Field(default=587, ge=1, le=65535, validation_alias="ALERT_SMTP_PORT")
    alert_smtp_username: str | None = Field(default=None, validation_alias="ALERT_SMTP_USERNAME")
    alert_smtp_password: str | None = Field(default=None, validation_alias="ALERT_SMTP_PASSWORD")
    alert_email_from: str | None = Field(default=None, validation_alias="ALERT_EMAIL_FROM")

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
