"""Pytest fixtures shared across the test suite.

Provides:

* ``client`` — HTTPX async client wired to the FastAPI ASGI app.
* ``db_session`` — an in-memory fake auth session for isolated DB tests.
* ``auth_client`` — an HTTPX client that has already registered and logged in,
  carrying a valid access token for protected endpoints.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_db_session
from app.auth.models import User
from app.main import app

# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


class _FakeAuthStore:
    """Very small in-memory store that mimics the auth database tables."""

    def __init__(self) -> None:
        self.users_by_id: dict[UUID, User] = {}
        self.users_by_email: dict[str, User] = {}


class _FakeScalarResult:
    def __init__(self, user: User | None) -> None:
        self._user = user

    def scalar_one_or_none(self) -> User | None:
        return self._user


class _FakeAsyncSession:
    """Minimal async session that supports the auth repository methods."""

    def __init__(self, store: _FakeAuthStore) -> None:
        self._store = store
        self._pending_user: User | None = None

    async def execute(self, statement) -> _FakeScalarResult:  # noqa: ANN001
        entity = statement.column_descriptions[0]["entity"]
        if entity is not User:
            raise NotImplementedError(f"Unsupported entity: {entity!r}")

        criteria = list(statement._where_criteria)
        if len(criteria) != 1:
            raise NotImplementedError("Expected a single equality predicate")

        criterion = criteria[0]
        column_name = getattr(criterion.left, "key", None)
        value = getattr(criterion.right, "value", None)

        user: User | None = None
        if column_name == "email":
            user = self._store.users_by_email.get(value)
        elif column_name == "id":
            user = self._store.users_by_id.get(value)
        else:
            raise NotImplementedError(f"Unsupported lookup column: {column_name!r}")

        return _FakeScalarResult(user)

    def add(self, user: User) -> None:
        self._pending_user = user

    async def commit(self) -> None:
        if self._pending_user is None:
            return

        user = self._pending_user
        if user.id is None:
            user.id = uuid4()
        if user.created_at is None:
            now = datetime.now(UTC)
            user.created_at = now
            user.updated_at = now
        if user.email in self._store.users_by_email:
            raise IntegrityError(None, None, Exception("duplicate email"))

        self._store.users_by_id[user.id] = user
        self._store.users_by_email[user.email] = user
        self._pending_user = None

    async def refresh(self, user: User) -> None:
        if user.id is not None:
            self._store.users_by_id[user.id] = user
        self._store.users_by_email[user.email] = user


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[_FakeAsyncSession]:
    """Yield a request-scoped fake auth session."""
    yield _FakeAsyncSession(_FakeAuthStore())


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session: _FakeAsyncSession) -> AsyncIterator[AsyncClient]:
    """HTTPX async client with the auth session overridden to in-memory storage.

    Uses ASGITransport so tests exercise the real application without
    binding a network port.
    """

    async def _override_session() -> AsyncIterator[_FakeAsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    """An HTTPX client that has registered and logged in.

    Returns the same client instance with the ``Authorization`` header set
    to a valid access token. Use this for protected-endpoint tests.
    """
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "testuser@example.com",
            "password": "Str0ngP@ss!",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 201
    tokens = response.json()["tokens"]
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    return client
