"""Reusable FastAPI dependencies for local JWT authentication.

These dependencies implement the FastAPI dependency-injection chain:

    ``get_current_user``      → decodes the JWT, loads the user.
    ``get_current_active_user`` → ensures the account is active.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.auth.jwt import decode_token
from app.auth.models import User
from app.auth.repository import AuthRepository
from app.core.logging import get_logger

logger = get_logger(__name__)

# Bearer scheme for OpenAPI documentation.  ``auto_error=False`` lets us
# return a custom error response rather than FastAPI's default 403.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """Decode the access token and return the authenticated :class:`User`.

    This is the foundational auth dependency. All other auth dependencies
    build on top of it.

    Raises
    ------
    HTTPException
        ``401`` if the token is missing, malformed, expired, or the user
        does not exist.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str = payload.get("sub", "")
    try:
        user_id = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed user identifier in token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    repo = AuthRepository(session)
    user = await repo.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Store on request state so downstream handlers (e.g. /auth/me) can
    # access the user without re-decoding.
    request.state.current_user = user

    logger.info(
        "user_authenticated",
        extra={"user_id": str(user.id), "email": user.email},
    )

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure the current user's account is active.

    Use this dependency for any endpoint that requires an authenticated,
    non-deactivated account.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated",
        )
    return current_user



