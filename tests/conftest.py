"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTPX async client wired directly to the FastAPI ASGI app.

    Uses ASGITransport so tests exercise the real application without
    binding a network port.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
