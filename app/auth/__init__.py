"""Local JWT authentication package.

This package provides local email/password authentication using JWT access
and refresh tokens. It intentionally does not include OAuth, SSO, or RBAC.

* :mod:`app.auth.models`       — SQLAlchemy ORM model (``User``).
* :mod:`app.auth.schemas`      — Pydantic v2 request / response schemas.
* :mod:`app.auth.security`     — Password hashing, token verification utilities.
* :mod:`app.auth.jwt`          — JWT creation and decoding.
* :mod:`app.auth.repository`   — Database access layer (queries only, no business logic).
* :mod:`app.auth.service`      — Business logic (registration, login, refresh, logout).
* :mod:`app.auth.router`       — FastAPI route definitions (thin controllers).
* :mod:`app.auth.dependencies` — Reusable FastAPI dependencies (current_user, active_user).
"""

from app.auth.dependencies import (
    get_current_active_user,
    get_current_user,
)
from app.auth.service import AuthService

__all__ = [
    "AuthService",
    "get_current_active_user",
    "get_current_user",
]
