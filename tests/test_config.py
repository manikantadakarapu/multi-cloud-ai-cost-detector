"""Tests for application configuration."""

from app.core.config import Settings


def test_aws_settings_defaults():
    """AWS settings have correct defaults and validation."""
    settings = Settings(
        JWT_SECRET_KEY="test-secret",
        AWS_DEFAULT_REGION="us-east-1",
        AWS_COST_EXPLORER_ENABLED=True,
    )
    assert settings.aws_default_region == "us-east-1"
    assert settings.aws_cost_explorer_enabled is True
    assert settings.aws_profile is None
    assert settings.aws_access_key_id is None
    assert settings.aws_secret_access_key is None


def test_aws_settings_from_env(monkeypatch):
    """AWS settings load from environment variables."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_PROFILE", "production")
    monkeypatch.setenv("AWS_COST_EXPLORER_ENABLED", "false")
    settings = Settings(JWT_SECRET_KEY="test-secret")
    assert settings.aws_default_region == "eu-west-1"
    assert settings.aws_profile == "production"
    assert settings.aws_cost_explorer_enabled is False


def test_gcp_billing_settings_defaults() -> None:
    """GCP billing settings have correct defaults and validation."""
    settings = Settings(JWT_SECRET_KEY="test-secret")
    assert settings.gcp_billing_enabled is True
    assert settings.google_application_credentials is None
    assert settings.gcp_billing_account is None
    assert settings.gcp_billing_project is None
    assert settings.gcp_billing_dataset is None
    assert settings.gcp_billing_table is None


def test_gcp_billing_settings_from_env(monkeypatch) -> None:
    """GCP billing settings load from environment variables."""
    monkeypatch.setenv("GCP_BILLING_ENABLED", "false")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/path/to/creds.json")
    monkeypatch.setenv("GCP_BILLING_ACCOUNT", "012345-678901-234567")
    monkeypatch.setenv("GCP_BILLING_PROJECT", "billing-project")
    monkeypatch.setenv("GCP_BILLING_DATASET", "billing_dataset")
    monkeypatch.setenv("GCP_BILLING_TABLE", "gcp_billing_export_v1")
    settings = Settings(JWT_SECRET_KEY="test-secret")
    assert settings.gcp_billing_enabled is False
    assert settings.google_application_credentials == "/path/to/creds.json"
    assert settings.gcp_billing_account == "012345-678901-234567"
    assert settings.gcp_billing_project == "billing-project"
    assert settings.gcp_billing_dataset == "billing_dataset"
    assert settings.gcp_billing_table == "gcp_billing_export_v1"


def test_shared_infrastructure_settings_defaults() -> None:
    """Shared infrastructure settings expose the new Sprint 0.7 defaults."""
    settings = Settings(JWT_SECRET_KEY="test-secret")
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.cache_ttl_seconds == 300
    assert settings.rate_limit_per_minute == 60
