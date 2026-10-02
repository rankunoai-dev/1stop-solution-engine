"""Shared fixtures for the API integration tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from src.modules.api.app import create_app
from src.modules.api.deps import get_db_conn


@pytest.fixture
def api_app(test_engine: AsyncEngine):
    """Create a test FastAPI app with the DB connection overridden.

    The ``get_db_conn`` dependency is replaced with one that uses the
    test engine (already migrated) so no network calls to production are made.
    """
    app = create_app()

    async def _override() -> AsyncGenerator[AsyncConnection, None]:
        async with test_engine.begin() as conn:
            yield conn

    app.dependency_overrides[get_db_conn] = _override
    return app


@pytest.fixture
async def client(api_app) -> AsyncGenerator[AsyncClient, None]:
    """Yield an HTTPX async test client for the API app."""
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as c:
        yield c
