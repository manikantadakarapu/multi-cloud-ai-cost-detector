"""Authentication business-logic service.

The service layer orchestrates registration, login, token refresh, logout,
and user retrieval. It is the **only** layer that applies business rules
(email uniqueness, password verification, token validation). Routers call
these methods and translate the results into HTTP responses.
"""

from __future__ import annotations

import uuid

import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.models import User
from app.auth.repository import AuthRepository
from app.auth.schemas import TokenResponse, UserResponse
from app.auth.security import hash_password, verify_password
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AuthError(Exception):
    """Base exception for authentication business-logic errors."""

    def __init__(self, detail: str, error_code: str = "AUTH_ERROR") -> None:
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class EmailAlreadyRegisteredError(AuthError):
    def __init__(self) -> None:
        super().__init__(
            detail="An account with this email address already exists.",
            error_code="EMAIL_ALREADY_REGISTERED",
        )


class InvalidCredentialsError(AuthError):
    def __init__(self) -> None:
        super().__init__(
            detail="Invalid email or password.",
            error_code="INVALID_CREDENTIALS",
        )


class UserInactiveError(AuthError):
    def __init__(self) -> None:
        super().__init__(
            detail="This account has been deactivated. Contact an administrator.",
            error_code="ACCOUNT_INACTIVE",
        )


class InvalidTokenError(AuthError):
    def __init__(self, detail: str = "Invalid or expired token.") -> None:
        super().__init__(detail=detail, error_code="INVALID_TOKEN")


class AuthService:
    """Orchestrates local email/password JWT authentication workflows.

    Each instance is constructed with a request-scoped :class:`AsyncSession`
    so the caller controls the session lifecycle. The repository is an
    implementation detail of the service.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = AuthRepository(session)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register(self, email: str, full_name: str, password: str) -> UserResponse:
        """Register a new user with email + password."""
        existing = await self._repo.get_user_by_email(email)
        if existing is not None:
            raise EmailAlreadyRegisteredError()

        user = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            is_active=True,
        )
        try:
            await self._repo.create_user(user)
        except IntegrityError:
            raise EmailAlreadyRegisteredError() from None

        logger.info(
            "user_registered",
            extra={"user_id": str(user.id), "email": user.email},
        )

        return _user_to_response(user)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def authenticate(self, email: str, password: str) -> TokenResponse:
        """Authenticate a user with email + password and return tokens."""
        user = await self._repo.get_user_by_email(email)
        if user is None or user.password_hash is None:
            raise InvalidCredentialsError()

        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise UserInactiveError()

        await self._repo.update_last_login(user.id)

        logger.info(
            "user_login",
            extra={"user_id": str(user.id), "email": user.email},
        )

        return _issue_tokens(user)

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Exchange a valid refresh token for a new access token.

        The same refresh token string is returned; rotation and revocation
        are intentionally not implemented for this simplified local auth
        layer.
        """
        try:
            payload = decode_token(refresh_token)
        except jwt.ExpiredSignatureError:
            raise InvalidTokenError("Refresh token has expired.") from None
        except jwt.InvalidTokenError:
            raise InvalidTokenError("Invalid refresh token.") from None

        if payload.get("type") != "refresh":
            raise InvalidTokenError("Expected a refresh token.")

        user_id_str = payload.get("sub", "")
        try:
            user_id = uuid.UUID(user_id_str)
        except (ValueError, TypeError):
            raise InvalidTokenError("Malformed user identifier in token.") from None

        user = await self._repo.get_user_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidTokenError("User not found or inactive.")

        access_token = create_access_token(
            user_id=user_id_str,
            email=user.email,
        )

        logger.info(
            "token_refreshed",
            extra={"user_id": str(user.id)},
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",  # nosec: B106 — OAuth2 token type identifier, not a password
            expires_in=settings.access_token_expire_minutes * 60,
        )

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    async def logout(self, refresh_token: str) -> bool:
        """Validate a refresh token and return a stateless logout success indicator.

        No token revocation or database state change is performed. The token
        is still decoded and validated so malformed, expired, or wrong-type
        refresh tokens return an error to the caller.
        """
        if not refresh_token:
            raise InvalidTokenError("Invalid refresh token.")

        try:
            payload = decode_token(refresh_token)
        except jwt.ExpiredSignatureError:
            raise InvalidTokenError("Refresh token has expired.") from None
        except jwt.InvalidTokenError:
            raise InvalidTokenError("Invalid refresh token.") from None

        if payload.get("type") != "refresh":
            raise InvalidTokenError("Expected a refresh token.")

        user_id_str = payload.get("sub", "")
        try:
            user_id = uuid.UUID(user_id_str)
        except (ValueError, TypeError):
            raise InvalidTokenError("Malformed user identifier in token.") from None

        user = await self._repo.get_user_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidTokenError("User not found or inactive.")

        logger.info("user_logout")
        return True

    # ------------------------------------------------------------------
    # User retrieval
    # ------------------------------------------------------------------

    async def get_current_user(self, user_id: uuid.UUID) -> UserResponse:
        """Fetch a user by id and verify the account is active."""
        user = await self._repo.get_user_by_id(user_id)
        if user is None:
            raise InvalidTokenError("User not found.")
        if not user.is_active:
            raise UserInactiveError()
        return _user_to_response(user)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _issue_tokens(user: User) -> TokenResponse:
    """Create an access + refresh token pair for a user."""
    user_id_str = str(user.id)
    access_token = create_access_token(
        user_id=user_id_str,
        email=user.email,
    )
    refresh_token, _jti, _expires_at = create_refresh_token(
        user_id=user_id_str,
        email=user.email,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",  # nosec: B106 — OAuth2 token type identifier, not a password
        expires_in=settings.access_token_expire_minutes * 60,
    )


def _user_to_response(user: User) -> UserResponse:
    """Map a :class:`User` model to the public response schema."""
    return UserResponse.model_validate(user)
