"""FastAPI application factory for the 1Stop API (R0.9 → R0.11).

Usage::

    # In production (e.g. via uvicorn or the CLI):
    uvicorn src.modules.api.app:app
    onestop serve --port 8000

    # In tests:
    from src.modules.api.app import create_app
    app = create_app()

The ``lifespan`` context manager bootstraps the initial admin user on startup
when ``BOOTSTRAP_ADMIN_EMAIL`` is configured.

CORS
----
In development (and when ``APP_URL`` is not set), all origins are allowed.
In production, only ``APP_URL`` is in the allow-list.

Exception handling
------------------
Unhandled exceptions are caught, logged, and returned as a generic 500
response so stack traces never leak to clients.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.config import Environment
from src.modules.api.routes_admin_jobs import router_admin_jobs
from src.modules.api.routes_admin_spend import router_admin_spend
from src.modules.api.routes_admin_users import router_admin_users
from src.modules.api.routes_auth import router_auth
from src.modules.api.routes_chat import router_chat
from src.modules.platform.auth import bootstrap_admin
from src.modules.platform.db import transaction
from src.modules.platform.settings import get_onestop_settings

__all__ = ["app", "create_app"]

_logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure a FastAPI application instance.

    Returns:
        A fully configured ``FastAPI`` application with all routers,
        CORS middleware, health endpoint, and global exception handler.
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

    # -- CORS -----------------------------------------------------------------
    s = get_onestop_settings()
    cors_origins: list[str] = (
        [s.app_url] if s.environment == Environment.PRODUCTION and s.app_url else ["*"]
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Global exception handler ---------------------------------------------
    @application.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        _logger.exception(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # -- Health ---------------------------------------------------------------
    @application.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """Return service health. No auth required."""
        return {"status": "ok"}

    # -- Routers --------------------------------------------------------------
    application.include_router(router_auth)
    application.include_router(router_admin_users)
    application.include_router(router_chat)
    application.include_router(router_admin_spend)
    application.include_router(router_admin_jobs)

    return application


app = create_app()
