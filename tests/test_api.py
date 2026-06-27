"""Smoke tests for the service root and API routing.

These do not touch the database and run against the ASGI app in-memory.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_returns_service_identity(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Multi-Cloud AI Cost Detective"
    assert body["version"]
    assert body["status"] == "running"
    assert body["docs"] == "/docs"
    assert body["health"] == "/api/v1/health"


@pytest.mark.asyncio
async def test_openapi_docs_available(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"] == "Multi-Cloud AI Cost Detective"
    assert "/api/v1/health" in spec["paths"]
