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
