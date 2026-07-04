"""OpenAPI / Swagger metadata.

Centralised so :mod:`app.main` stays focused on application wiring and the
documentation strings can be maintained independently of route code.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import settings

API_DESCRIPTION = (
    "Multi-Cloud AI Cost Detective is a backend platform that ingests cost "
    "data across AWS, Azure, and Google Cloud Platform, detects anomalies, "
    "and surfaces AI-powered recommendations to reduce cloud waste.\n\n"
    "Phase 1 ships the production foundation: a FastAPI application factory, "
    "async SQLAlchemy 2.x, PostgreSQL connectivity, Alembic migrations, "
    "structured JSON logging, and a health endpoint."
)

OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "health",
        "description": "Service readiness and dependency probes.",
    },
    {
        "name": "root",
        "description": "Service discovery and identity.",
    },
    {
        "name": "auth",
        "description": "Authentication and authorization — registration, login, token refresh, logout, and user profile.",
    },
]


def configure_openapi(application: FastAPI) -> None:
    """Attach rich OpenAPI metadata to a FastAPI application instance."""
    application.title = settings.app_name
    application.description = API_DESCRIPTION
    application.version = settings.app_version
    application.contact = {
        "name": "Multi-Cloud AI Cost Detective Maintainers",
        "url": "https://github.com/your-org/MCAICD",
        "email": "maintainers@example.com",
    }
    application.license_info = {
        "name": "MIT License",
        "url": "https://opensource.org/license/mit",
    }
    application.openapi_tags = OPENAPI_TAGS
