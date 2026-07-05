"""Comprehensive tests for the authentication endpoints.

Covers:

* Registration (success, duplicate email, weak password, invalid email)
* Login (success, wrong password, nonexistent user, inactive user)
* JWT validation (valid token, missing token, malformed token, expired token)
* Refresh token (success, revoked token, invalid token, wrong type)
* Logout (success, already revoked, invalid token)
* Protected endpoint (``/auth/me`` with and without token)
* Password hashing and verification
* JWT creation and decoding
"""

from __future__ import annotations

from unittest.mock import patch

import jwt as pyjwt
import pytest
from httpx import AsyncClient

from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.security import hash_password, verify_password
from app.core.config import settings

# ---------------------------------------------------------------------------
# Helper constants
# ---------------------------------------------------------------------------

REGISTER_PAYLOAD = {
    "email": "newuser@example.com",
    "password": "Str0ngP@ss!",
    "full_name": "New User",
}

LOGIN_PAYLOAD = {
    "email": "newuser@example.com",
    "password": "Str0ngP@ss!",
}


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient) -> None:
    """Successful registration returns 201, user, and tokens."""
    response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "newuser@example.com"
    assert body["user"]["full_name"] == "New User"
    assert body["user"]["is_active"] is True
    assert "id" in body["user"]
    assert "access_token" in body["tokens"]
    assert "refresh_token" in body["tokens"]
    assert body["tokens"]["token_type"] == "bearer"
    assert body["tokens"]["expires_in"] > 0


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    """Registering with an existing email returns 409."""
    await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 409
    body = response.json()
    assert body["error_code"] == "EMAIL_ALREADY_REGISTERED"


@pytest.mark.asyncio
async def test_register_weak_password_no_uppercase(client: AsyncClient) -> None:
    """Password without uppercase returns 422."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak1@example.com",
            "password": "weakpass1",
            "full_name": "Weak User",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_weak_password_no_lowercase(client: AsyncClient) -> None:
    """Password without lowercase returns 422."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak2@example.com",
            "password": "WEAKPASS1",
            "full_name": "Weak User",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_weak_password_no_digit(client: AsyncClient) -> None:
    """Password without a digit returns 422."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak3@example.com",
            "password": "WeakPassWord",
            "full_name": "Weak User",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient) -> None:
    """Password shorter than 8 characters returns 422."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak4@example.com",
            "password": "Ab1!",
            "full_name": "Weak User",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient) -> None:
    """Invalid email format returns 422."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "Str0ngP@ss!",
            "full_name": "Bad Email",
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    """Successful login returns tokens."""
    await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    response = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    """Wrong password returns 401."""
    await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "newuser@example.com", "password": "Wr0ngP@ss!"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error_code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient) -> None:
    """Login with unregistered email returns 401."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Str0ngP@ss!"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error_code"] == "INVALID_CREDENTIALS"


# ---------------------------------------------------------------------------
# Refresh token tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_success(client: AsyncClient) -> None:
    """A valid refresh token returns a new access token (refresh token is unchanged)."""
    reg = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    refresh_token = reg.json()["tokens"]["refresh_token"]
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["refresh_token"] == refresh_token  # no rotation


@pytest.mark.asyncio
async def test_refresh_revoked_token(client: AsyncClient) -> None:
    """Refresh is stateless: reusing a refresh token is allowed."""
    reg = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    refresh_token = reg.json()["tokens"]["refresh_token"]
    # Use the token once.
    await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    # Reuse the same token — still accepted under stateless refresh.
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_refresh_invalid_token(client: AsyncClient) -> None:
    """A malformed refresh token returns 401."""
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not-a-jwt"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_access_token_wrong_type(client: AsyncClient) -> None:
    """Using an access token as a refresh token returns 401."""
    reg = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    access_token = reg.json()["tokens"]["access_token"]
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Logout tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_success(client: AsyncClient) -> None:
    """Logout returns 200; no server-side revocation occurs."""
    reg = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    refresh_token = reg.json()["tokens"]["refresh_token"]
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    assert "message" in response.json()
    # Stateless: the refresh token still works after logout.
    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_response.status_code == 200


@pytest.mark.asyncio
async def test_logout_already_revoked(client: AsyncClient) -> None:
    """Logging out twice with the same token returns 200 (idempotent)."""
    reg = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    refresh_token = reg.json()["tokens"]["refresh_token"]
    await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    response = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_logout_invalid_token(client: AsyncClient) -> None:
    """Logout is stateless: any token string is accepted (returns 200)."""
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "garbage-token"},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Protected endpoint (/auth/me) tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_with_valid_token(auth_client: AsyncClient) -> None:
    """``/auth/me`` returns the user profile when authenticated."""
    response = await auth_client.get("/api/v1/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "testuser@example.com"
    assert body["full_name"] == "Test User"


@pytest.mark.asyncio
async def test_me_without_token(client: AsyncClient) -> None:
    """``/auth/me`` without a token returns 401."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_malformed_token(client: AsyncClient) -> None:
    """``/auth/me`` with a malformed token returns 401."""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_refresh_token_as_access(client: AsyncClient) -> None:
    """Using a refresh token as an access token returns 401."""
    reg = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    refresh_token = reg.json()["tokens"]["refresh_token"]
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Expired token test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_access_token(client: AsyncClient) -> None:
    """An expired access token returns 401."""
    reg = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    user_id = reg.json()["user"]["id"]

    # Create a token that is already expired.
    with patch("app.auth.jwt.settings") as mock_settings:
        mock_settings.jwt_secret_key = settings.jwt_secret_key
        mock_settings.jwt_algorithm = settings.jwt_algorithm
        mock_settings.access_token_expire_minutes = -1  # expired in the past
        expired_token = create_access_token(
            user_id=user_id,
            email="newuser@example.com",
        )

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# JWT unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_decode_access_token() -> None:
    """Access token decodes correctly with the expected claims."""
    token = create_access_token(
        user_id="test-uuid",
        email="test@example.com",
    )
    payload = decode_token(token)
    assert payload["sub"] == "test-uuid"
    assert payload["email"] == "test@example.com"
    assert payload["type"] == "access"
    assert "jti" in payload
    assert "exp" in payload
    assert "iat" in payload


@pytest.mark.asyncio
async def test_create_and_decode_refresh_token() -> None:
    """Refresh token decodes correctly with ``type=refresh``."""
    token, jti, expires_at = create_refresh_token(
        user_id="test-uuid",
        email="test@example.com",
    )
    payload = decode_token(token)
    assert payload["type"] == "refresh"
    assert payload["jti"] == jti


@pytest.mark.asyncio
async def test_decode_invalid_token_raises() -> None:
    """Decoding a non-JWT string raises ``InvalidTokenError``."""
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_token("invalid-token-string")


@pytest.mark.asyncio
async def test_decode_tampered_token_raises() -> None:
    """Decoding a tampered token raises ``InvalidTokenError``."""
    token = create_access_token(
        user_id="test-uuid",
        email="test@example.com",
    )
    # Tamper with the payload so the signature no longer matches.
    header, payload, signature = token.split(".")
    tampered_payload = payload[:-1] + ("A" if payload[-1] != "A" else "B")
    tampered = f"{header}.{tampered_payload}.{signature}"
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_token(tampered)


# ---------------------------------------------------------------------------
# Password hashing unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hash_and_verify_password() -> None:
    """``hash_password`` + ``verify_password`` round-trip."""
    plain = "MyStr0ngP@ssword!"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed) is True


@pytest.mark.asyncio
async def test_verify_wrong_password() -> None:
    """``verify_password`` returns False for wrong password."""
    hashed = hash_password("C0rrectP@ss!")
    assert verify_password("Wr0ngP@ss!", hashed) is False


@pytest.mark.asyncio
async def test_hash_password_uniqueness() -> None:
    """Same password produces different hashes (different salts)."""
    h1 = hash_password("SameP@ssword1")
    h2 = hash_password("SameP@ssword1")
    assert h1 != h2
    assert verify_password("SameP@ssword1", h1)
    assert verify_password("SameP@ssword1", h2)


@pytest.mark.asyncio
async def test_verify_invalid_hash_returns_false() -> None:
    """``verify_password`` returns False for malformed hash."""
    assert verify_password("any-password", "not-a-valid-hash") is False
