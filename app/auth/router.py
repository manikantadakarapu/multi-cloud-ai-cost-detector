"""FastAPI route definitions for authentication.

All routes are mounted under the ``/api/v1/auth`` prefix (see
:mod:`app.api.router`).  Each handler is thin: it validates input via
Pydantic, delegates to :class:`AuthService`, and translates service
exceptions into appropriate HTTP responses.

Error handling convention
-------------------------
:class:`~app.auth.service.AuthError` subclasses are caught locally and mapped
to specific HTTP status codes and JSON bodies matching the
:class:`~app.auth.schemas.ErrorResponse` schema.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.auth.dependencies import get_current_active_user
from app.auth.jwt import create_access_token, create_refresh_token
from app.auth.models import User
from app.auth.schemas import (
    ErrorResponse,
    LogoutRequest,
    MessageResponse,
    TokenRefreshRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserRegisterResponse,
    UserResponse,
)
from app.auth.service import (
    AuthError,
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
    UserInactiveError,
)
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Error response helper
# ---------------------------------------------------------------------------


def _error_response(
    exc: AuthError,
    status_code: int,
) -> tuple[ErrorResponse, int]:
    return ErrorResponse(detail=exc.detail, error_code=exc.error_code), status_code


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=UserRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Create a new user account with email and password.\n\n"
        "**Validation:**\n"
        "- Email must be valid and unique.\n"
        "- Password must be at least 8 characters, with one uppercase letter, "
        "one lowercase letter, and one digit.\n\n"
        "On success, returns the created user and an initial access + refresh "
        "token pair."
    ),
    responses={
        201: {
            "description": "User registered successfully.",
            "model": UserRegisterResponse,
        },
        409: {
            "description": "Email already registered.",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An account with this email address already exists.",
                        "error_code": "EMAIL_ALREADY_REGISTERED",
                    }
                }
            },
        },
        422: {
            "description": "Validation error (invalid email or weak password).",
            "model": dict,
        },
    },
)
async def register(
    payload: UserRegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRegisterResponse:
    """Register a new user."""
    service = AuthService(session)
    try:
        user = await service.register(
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
        )
    except EmailAlreadyRegisteredError as exc:
        body, code = _error_response(exc, status.HTTP_409_CONFLICT)
        return JSONResponse(status_code=code, content=body.model_dump())
    user_id_str = str(user.id)
    access_token = create_access_token(user_id=user_id_str, email=user.email)
    refresh_token, _jti, _expires_at = create_refresh_token(user_id=user_id_str, email=user.email)
    tokens = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",  # nosec: B106 — OAuth2 token type identifier, not a password
        expires_in=settings.access_token_expire_minutes * 60,
    )
    return UserRegisterResponse(user=user, tokens=tokens)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and obtain tokens",
    description=(
        "Authenticate with email and password. On success returns a "
        "short-lived access token and a long-lived refresh token.\n\n"
        "**Security note:** Invalid credentials always return HTTP 401 with a "
        "generic message to prevent email enumeration."
    ),
    responses={
        200: {
            "description": "Authentication successful.",
            "model": TokenResponse,
        },
        401: {
            "description": "Invalid credentials.",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid email or password.",
                        "error_code": "INVALID_CREDENTIALS",
                    }
                }
            },
        },
        403: {
            "description": "Account deactivated.",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "detail": "This account has been deactivated. Contact an administrator.",
                        "error_code": "ACCOUNT_INACTIVE",
                    }
                }
            },
        },
    },
)
async def login(
    payload: UserLoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """Login with email + password."""
    service = AuthService(session)
    try:
        tokens = await service.authenticate(email=payload.email, password=payload.password)
    except UserInactiveError as exc:
        body, code = _error_response(exc, status.HTTP_403_FORBIDDEN)
        return JSONResponse(status_code=code, content=body.model_dump())
    except InvalidCredentialsError as exc:
        body, code = _error_response(exc, status.HTTP_401_UNAUTHORIZED)
        return JSONResponse(status_code=code, content=body.model_dump())
    return tokens


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description=(
        "Exchange a valid refresh token for a new access token. The same "
        "refresh token is returned; no replacement or server-side invalidation occurs."
    ),
    responses={
        200: {
            "description": "New access token issued.",
            "model": TokenResponse,
        },
        401: {
            "description": "Invalid or expired refresh token.",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid or expired token.",
                        "error_code": "INVALID_TOKEN",
                    }
                }
            },
        },
    },
)
async def refresh(
    payload: TokenRefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """Exchange a refresh token for a new access token."""
    service = AuthService(session)
    try:
        tokens = await service.refresh(payload.refresh_token)
    except InvalidTokenError as exc:
        body, code = _error_response(exc, status.HTTP_401_UNAUTHORIZED)
        return JSONResponse(status_code=code, content=body.model_dump())
    return tokens


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout",
    description=(
        "Perform a stateless logout. No server-side token invalidation occurs; "
        "clients should discard the refresh token and access token locally."
    ),
    responses={
        200: {
            "description": "Logout successful.",
            "model": MessageResponse,
            "content": {"application/json": {"example": {"message": "Successfully logged out."}}},
        },
        401: {
            "description": "Invalid refresh token.",
            "model": ErrorResponse,
        },
    },
)
async def logout(
    payload: LogoutRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """Log the user out statelessly."""
    service = AuthService(session)
    try:
        await service.logout(refresh_token=payload.refresh_token)
    except InvalidTokenError as exc:
        body, code = _error_response(exc, status.HTTP_401_UNAUTHORIZED)
        return JSONResponse(status_code=code, content=body.model_dump())
    return MessageResponse(message="Successfully logged out.")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description=(
        "Returns the authenticated user's profile. Requires a valid access "
        "token in the ``Authorization: Bearer <token>`` header."
    ),
    responses={
        200: {
            "description": "Current user profile.",
            "model": UserResponse,
        },
        401: {
            "description": "Missing or invalid token.",
            "model": ErrorResponse,
            "content": {
                "application/json": {"example": {"detail": "Not authenticated", "error_code": None}}
            },
        },
    },
)
async def me(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    """Return the current authenticated user's profile."""
    service = AuthService(session)
    return await service.get_current_user(current_user.id)
