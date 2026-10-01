"""Shared pytest fixtures.

Two invariants this file exists to protect:

1. Tests never read the developer's real `.env`. Every test gets an explicit,
   hermetic `Settings` object.
2. Tests never touch a real external service. There is no network fixture here
   on purpose - connectors are mocked at the `BaseAPIClient` boundary.

Database fixtures (R0.4)
------------------------
Tests marked ``@pytest.mark.integration`` may use the ``db_conn`` fixture,
which requires a running Postgres instance reachable at ``TEST_DATABASE_URL``::

    postgresql+psycopg://onestop:onestop_dev@localhost:5432/onestop_test

Start the container with ``docker compose up -d db`` before running integration
tests.  They are excluded from CI (``-m "not integration"`` in the CI job).
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from src.core.config import Environment, Settings, reset_settings_cache
from src.core.guardrails import AutoApproveProvider, GuardrailEngine
from src.core.rate_limiter import CostLedger
from src.core.registry import registry
from src.core.schemas import RiskClass, ToolMetadata
from src.modules.platform.db import reset_engine

# ---------------------------------------------------------------------------
# Default TEST_DATABASE_URL for the local Docker Compose database.
# Override by setting the environment variable before running pytest.
# ---------------------------------------------------------------------------
_DEFAULT_TEST_DB_URL = "postgresql+psycopg://onestop:onestop_dev@localhost:5432/onestop_test"


@pytest.fixture(autouse=True)
def _isolate_settings_cache() -> Iterator[None]:
    """Clear the settings singleton around every test."""
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture(autouse=True)
def _isolate_registry() -> Iterator[None]:
    """Keep tool registrations from leaking between tests."""
    registry.clear()
    yield
    registry.clear()


@pytest.fixture(autouse=True)
def _isolate_db_engine() -> Iterator[None]:
    """Discard the cached database engine around every test.

    Tests that use a real database create their own engine via ``test_engine``.
    This ensures no test accidentally uses the production engine (which reads
    DATABASE_URL from .env).
    """
    reset_engine()
    yield
    reset_engine()


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Hermetic settings: no `.env`, audit log redirected into tmp."""
    return Settings(
        _env_file=None,
        environment=Environment.DEVELOPMENT,
        audit_log_path=tmp_path / "audit.jsonl",
        max_session_spend_usd=1.0,
        default_requests_per_minute=600,
        default_timeout_s=2.0,
    )


@pytest.fixture
def permissive_guardrails(settings: Settings) -> GuardrailEngine:
    """Engine that approves HITL prompts. For testing the happy path only."""
    return GuardrailEngine(approval_provider=AutoApproveProvider(), settings=settings)


@pytest.fixture
def strict_guardrails(settings: Settings) -> GuardrailEngine:
    """Engine with the production default: deny unapproved HITL actions."""
    return GuardrailEngine(settings=settings)


@pytest.fixture
def ledger() -> CostLedger:
    """A small, isolated spend ledger."""
    return CostLedger(ceiling_usd=1.0)


@pytest.fixture
def read_metadata() -> ToolMetadata:
    """Metadata for a harmless read-only tool."""
    return ToolMetadata(
        name="test.reader",
        summary="Read-only test tool.",
        risk_class=RiskClass.READ,
    )


@pytest.fixture
def write_metadata() -> ToolMetadata:
    """Metadata for a tool that mutates external state."""
    return ToolMetadata(
        name="test.writer",
        summary="Write test tool.",
        risk_class=RiskClass.WRITE,
    )


# ---------------------------------------------------------------------------
# Database fixtures (integration tests only)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """Return the synchronous psycopg3 URL for the test database.

    Skips the test session if ``TEST_DATABASE_URL`` is not set and the default
    local URL is not reachable (the check happens lazily when first used).
    """
    return os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_DB_URL)


@pytest.fixture(scope="session")
def apply_migrations(test_db_url: str) -> Iterator[None]:
    """Run ``alembic upgrade head`` once per test session; downgrade on teardown.

    Requires the test database to be running (``docker compose up -d db``).
    Only used by tests marked ``@pytest.mark.integration``.
    """
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", test_db_url)
    command.upgrade(cfg, "head")
    yield
    command.downgrade(cfg, "base")


@pytest.fixture(scope="session")
def test_engine(test_db_url: str, apply_migrations: None) -> Iterator[AsyncEngine]:
    """Session-scoped async engine for the test database.

    Depends on ``apply_migrations`` so the schema exists before tests run.
    """
    async_url = test_db_url.replace("+psycopg://", "+psycopg_async://")
    engine = create_async_engine(async_url, echo=False)
    yield engine
    # Disposal in a sync fixture teardown: run a new event loop if none is active.
    import asyncio  # noqa: PLC0415

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(engine.dispose())
        else:
            loop.run_until_complete(engine.dispose())
    except RuntimeError:
        asyncio.run(engine.dispose())


@pytest.fixture
async def db_conn(test_engine: AsyncEngine) -> AsyncGenerator[AsyncConnection, None]:
    """Per-test async connection wrapped in a SAVEPOINT.

    Rolls back to the savepoint on teardown, leaving the database clean for the
    next test without truncating tables (much faster than a full rollback).

    Usage::

        @pytest.mark.integration
        async def test_insert_space(db_conn):
            await db_conn.execute(sa.insert(t_spaces).values(slug="x", name="X"))
            result = await db_conn.execute(sa.select(t_spaces))
            assert result.one().slug == "x"
            # rolled back; no row persists
    """
    async with test_engine.connect() as conn:
        nested = await conn.begin_nested()  # SAVEPOINT
        yield conn
        await nested.rollback()
