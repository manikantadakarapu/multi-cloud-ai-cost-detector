"""Pydantic v2 request / response schemas for authentication.

All response schemas use ``ConfigDict(extra="forbid")`` to prevent schema
drift. Request models allow ``extra="ignore"`` by default so unexpected
fields do not break parsing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class UserRegisterRequest(BaseModel):
    """Payload for ``POST /api/v1/auth/register``."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(
        ...,
        description="User email address. Must be unique.",
        examples=["user@example.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description=(
            "Password. Must be at least 8 characters and contain at least "
            "one uppercase letter, one lowercase letter, and one digit."
        ),
        examples=["Str0ngP@ss!"],
    )
    full_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="User full display name.",
        examples=["Jane Doe"],
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Enforce a minimum password policy.

        The policy requires at least:
        * 8 characters (enforced by ``Field(min_length=8)``)
        * one uppercase letter
        * one lowercase letter
        * one digit
        """
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        return v


class UserLoginRequest(BaseModel):
    """Payload for ``POST /api/v1/auth/login``."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(
        ...,
        description="Registered email address.",
        examples=["user@example.com"],
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Account password.",
        examples=["Str0ngP@ss!"],
    )


class TokenRefreshRequest(BaseModel):
    """Payload for ``POST /api/v1/auth/refresh``."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(
        ...,
        description="A valid refresh token issued by /auth/login or /auth/refresh.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )


class LogoutRequest(BaseModel):
    """Payload for ``POST /api/v1/auth/logout``."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(
        ...,
        description=(
            "Refresh token being discarded on logout. Tokens are stateless; "
            "the client is responsible for removing stored copies."
        ),
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    """Access + refresh token pair returned by login, register, and refresh."""

    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(
        ...,
        description="Short-lived JWT access token. Send as ``Authorization: Bearer <token>``.",
    )
    refresh_token: str = Field(
        ...,
        description="Long-lived JWT refresh token. Use with ``POST /api/v1/auth/refresh``.",
    )
    token_type: Literal["bearer"] = Field(
        default="bearer",
        description="Token type. Always ``bearer``.",
    )
    expires_in: int = Field(
        ...,
        description="Access token lifetime in seconds.",
        examples=[1800],
    )


class UserResponse(BaseModel):
    """Public user representation returned by ``/auth/me`` and ``/auth/register``."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID = Field(..., description="User UUID primary key.")
    email: EmailStr = Field(..., description="User email address.")
    full_name: str = Field(..., description="Display name.")
    is_active: bool = Field(..., description="Whether the account is active.")
    created_at: datetime = Field(..., description="Account creation timestamp (UTC).")
    updated_at: datetime = Field(..., description="Last update timestamp (UTC).")
    last_login_at: datetime | None = Field(
        None, description="Last successful login timestamp (UTC), or null."
    )


class UserRegisterResponse(BaseModel):
    """Response for successful registration — includes user + tokens."""

    model_config = ConfigDict(extra="forbid")

    user: UserResponse = Field(..., description="The newly created user.")
    tokens: TokenResponse = Field(..., description="Initial access + refresh token pair.")


class MessageResponse(BaseModel):
    """Generic message response (e.g. logout success)."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., description="Human-readable status message.")


# ---------------------------------------------------------------------------
# Error schemas
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Standard error envelope for all auth endpoints.

    Every auth error response follows this shape so clients can parse errors
    consistently regardless of the endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    detail: str = Field(..., description="Human-readable error message.")
    error_code: str | None = Field(
        None,
        description="Machine-readable error code for programmatic handling.",
        examples=["INVALID_CREDENTIALS", "EMAIL_ALREADY_REGISTERED"],
    )
