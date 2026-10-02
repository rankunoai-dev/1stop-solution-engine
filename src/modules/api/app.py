"""FastAPI application factory for the 1Stop API (R0.9).

Usage::

    # In production (e.g. via uvicorn):
    uvicorn src.modules.api.app:app

    # In tests:
    from src.modules.api.app import create_app
    app = create_app()

The ``lifespan`` context manager bootstraps the initial admin user on startup
when ``BOOTSTRAP_ADMIN_EMAIL`` is configured.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.modules.api.routes_admin_users import router_admin_users
from src.modules.api.routes_auth import router_auth
from src.modules.platform.auth import bootstrap_admin
from src.modules.platform.db import transaction
from src.modules.platform.settings import get_onestop_settings

__all__ = ["app", "create_app"]


def create_app() -> FastAPI:
    """Create and configure a FastAPI application instance.

    Returns:
        A fully configured ``FastAPI`` application with auth and admin routers
        registered and an admin-bootstrap lifespan hook.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Run startup/shutdown hooks."""
        _ = app  # FastAPI passes the app; not used here
        s = get_onestop_settings()
        if s.bootstrap_admin_email:
            async with transaction() as conn:
                await bootstrap_admin(conn, s.bootstrap_admin_email)
        yield

    application = FastAPI(title="1Stop API", lifespan=lifespan)
    application.include_router(router_auth)
    application.include_router(router_admin_users)
    return application


app = create_app()
