"""JWT token creation and decoding.

Implements:

* **Access tokens** — short-lived (default 30 min), carry the user's identity
  and basic claims for authorization.
* **Refresh tokens** — long-lived (default 7 days), used only to obtain new
  access tokens. Each carries a unique ``jti`` for identification.

Both token types use the same secret and algorithm (HS256 by default) but are
distinguished by the ``type`` claim to prevent a refresh token from being
accepted as an access token and vice-versa.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypedDict

import jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]


class TokenData(TypedDict):
    """Decoded JWT payload, typed for internal use."""

    sub: str
    type: TokenType
    jti: str
    exp: int
    iat: int
    email: str


def _create_token(
    *,
    user_id: str,
    email: str,
    token_type: TokenType,
    expires_delta: timedelta,
) -> tuple[str, str]:
    """Create a signed JWT and return ``(token, jti)``.

    The ``jti`` (JWT ID) is a random UUID unique to each token. It is stored
    in the token payload for identification and future extension points.
    """
    now = datetime.now(UTC)
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": now + expires_delta,
        "email": email,
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, jti


def create_access_token(*, user_id: str, email: str) -> str:
    """Create a short-lived access token."""
    token, _ = _create_token(
        user_id=user_id,
        email=email,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return token


def create_refresh_token(*, user_id: str, email: str) -> tuple[str, str, datetime]:
    """Create a long-lived refresh token.

    Returns
    -------
    tuple[str, str, datetime]
        ``(token, jti, expires_at)`` — ``expires_at`` is exposed for the
        caller's convenience.
    """
    expires_delta = timedelta(days=settings.refresh_token_expire_days)
    expires_at = datetime.now(UTC) + expires_delta
    token, jti = _create_token(
        user_id=user_id,
        email=email,
        token_type="refresh",
        expires_delta=expires_delta,
    )
    return token, jti, expires_at


def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT.

    Parameters
    ----------
    token:
        The encoded JWT string.

    Returns
    -------
    TokenData
        The decoded payload as a typed dict.

    Raises
    ------
    jwt.ExpiredSignatureError
        If the token has expired.
    jwt.InvalidTokenError
        If the signature is invalid, the payload is malformed, or the
        ``type`` claim is missing.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    if "sub" not in payload or "type" not in payload:
        raise jwt.InvalidTokenError("Missing required claims")
    return payload  # type: ignore[return-value]
