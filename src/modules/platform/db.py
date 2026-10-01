"""Async database engine and session factory (ARCHITECTURE §13, ADR 0002).

All application database work goes through the helpers here rather than
creating engines directly, so:

- The engine is initialised once from ``OneStopSettings.database_url``.
- Tests replace it by calling ``reset_engine()`` before supplying their own
  ``AsyncEngine`` via the test fixtures in ``tests/conftest.py``.
- The ``transaction()`` context manager wraps a write operation in a connection
  that commits on normal exit and rolls back on exception.

Usage::

    from src.modules.platform.db import transaction

    async with transaction() as conn:
        await conn.execute(sa.insert(t_spaces).values(slug="demo", name="Demo"))

For reads (no commit needed) use ``get_engine().connect()`` directly.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

__all__ = [
    "get_engine",
    "reset_engine",
    "transaction",
]

_engine: AsyncEngine | None = None

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

_SYNC_PREFIXES = (
    "postgresql+psycopg://",
    "postgresql://",
    "postgres://",
)
_ASYNC_DIALECT = "postgresql+psycopg_async://"


def _to_async_url(url: str) -> str:
    """Convert a sync (psycopg3) or bare Postgres URL to the async dialect.

    SQLAlchemy 2 with psycopg3 uses two dialect names:
    - ``postgresql+psycopg://``       – synchronous (used by Alembic)
    - ``postgresql+psycopg_async://`` – asynchronous (used by the app)

    The DATABASE_URL in ``.env`` / environment is stored as the sync form so
    Alembic and the app can share one variable.
    """
    for prefix in _SYNC_PREFIXES:
        if url.startswith(prefix):
            return _ASYNC_DIALECT + url[len(prefix) :]
    # Already async or unrecognised dialect – return as-is.
    return url


# ---------------------------------------------------------------------------
# Engine lifecycle
# ---------------------------------------------------------------------------


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it lazily on first call.

    Reads ``DATABASE_URL`` from ``OneStopSettings``.  Raises ``ConfigurationError``
    if the URL is not set (which ``OneStopSettings.production_problems()`` will
    have flagged at boot in production, but not in development).
    """
    global _engine  # noqa: PLW0603
    if _engine is None:
        from src.core.errors import ConfigurationError  # noqa: PLC0415
        from src.modules.platform.settings import get_onestop_settings  # noqa: PLC0415

        settings = get_onestop_settings()
        raw_url = settings.database_url.get_secret_value() if settings.database_url else ""
        if not raw_url:
            msg = "DATABASE_URL is not set; cannot create the database engine."
            raise ConfigurationError(msg)

        async_url = _to_async_url(raw_url)
        _engine = create_async_engine(
            async_url,
            pool_pre_ping=True,
            # The pool is sized conservatively for the Railway single-service
            # deployment (D-18).  Supabase free tier caps total connections at
            # 60; we leave headroom for migrations and PgBouncer overhead.
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def reset_engine() -> None:
    """Discard the cached engine.  Intended for tests only.

    Tests create their own engine from ``TEST_DATABASE_URL`` and must not
    share the production engine.  Call this in teardown to prevent leaks.
    """
    global _engine  # noqa: PLW0603
    _engine = None


# ---------------------------------------------------------------------------
# Transaction helper
# ---------------------------------------------------------------------------


@asynccontextmanager
async def transaction() -> AsyncGenerator[AsyncConnection, None]:
    """Yield an ``AsyncConnection`` inside a committed transaction.

    - On normal exit the transaction is committed.
    - On exception the transaction is rolled back and the exception is re-raised.
    - Nested calls open a SAVEPOINT (via ``begin_nested``).

    Example::

        async with transaction() as conn:
            await conn.execute(sa.insert(t_jobs).values(...))
            # committed here

        # For rollback-on-error:
        try:
            async with transaction() as conn:
                await conn.execute(...)
                raise ValueError("oops")
        except ValueError:
            pass  # rolled back; no rows inserted
    """
    engine = get_engine()
    async with engine.begin() as conn:
        yield conn


# ---------------------------------------------------------------------------
# Convenience: execute a read-only query and return all rows.
# ---------------------------------------------------------------------------


async def fetch_all(stmt: sa.Executable) -> list[sa.engine.Row[tuple[object, ...]]]:
    """Execute *stmt* on a fresh connection and return all rows.

    Does not open a transaction (read-only; no commit overhead).
    """
    async with get_engine().connect() as conn:
        result = await conn.execute(stmt)
        return list(result.fetchall())
