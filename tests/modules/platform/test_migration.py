"""Integration tests for migration 0001: platform tables.

Requires a running Postgres + pgvector instance at TEST_DATABASE_URL
(default: the local Docker Compose container).

    docker compose up -d db
    pytest -m integration tests/modules/platform/test_migration.py

These tests are excluded from CI (``-m "not integration"``).
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _table_exists(conn: AsyncConnection, table: str) -> bool:
    """Check whether *table* exists in the ``onestop`` schema."""
    result = await conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'onestop' AND table_name = :t"
        ),
        {"t": table},
    )
    return result.scalar() == 1


async def _index_exists(conn: AsyncConnection, index: str) -> bool:
    """Check whether *index* exists in the ``onestop`` schema."""
    result = await conn.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE schemaname = 'onestop' AND indexname = :i"),
        {"i": index},
    )
    return result.scalar() == 1


async def _extension_exists(conn: AsyncConnection, ext: str) -> bool:
    result = await conn.execute(
        sa.text("SELECT 1 FROM pg_extension WHERE extname = :e"),
        {"e": ext},
    )
    return result.scalar() == 1


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMigration0001:
    """Upgrade → downgrade → upgrade round-trip; schema content checks."""

    async def test_extensions_installed(self, db_conn: AsyncConnection):
        for ext in ("vector", "pg_trgm", "citext", "pgcrypto"):
            assert await _extension_exists(db_conn, ext), f"extension missing: {ext}"

    async def test_all_platform_tables_exist(self, db_conn: AsyncConnection):
        tables = (
            "spaces",
            "users",
            "login_codes",
            "sessions",
            "llm_calls",
            "jobs",
            "schedules",
            "rate_limits",
            "email_deliveries",
            "audit_log",
            "settings_kv",
        )
        for t in tables:
            assert await _table_exists(db_conn, t), f"table missing: onestop.{t}"

    async def test_key_indexes_exist(self, db_conn: AsyncConnection):
        for idx in (
            "idx_login_codes_active",
            "idx_sessions_active",
            "idx_llm_calls_day",
            "idx_llm_calls_purpose_day",
            "idx_jobs_claimable",
            "idx_audit_log_at",
            "idx_audit_log_actor",
        ):
            assert await _index_exists(db_conn, idx), f"index missing: {idx}"

    async def test_internal_space_seeded(self, db_conn: AsyncConnection):
        result = await db_conn.execute(
            sa.text("SELECT slug FROM onestop.spaces WHERE slug = 'internal'")
        )
        assert result.scalar() == "internal"

    async def test_schedules_seeded(self, db_conn: AsyncConnection):
        result = await db_conn.execute(sa.text("SELECT name FROM onestop.schedules ORDER BY name"))
        names = [r[0] for r in result.fetchall()]
        assert "housekeeping" in names
        assert "weekly_sync" in names

    async def test_llm_calls_day_is_generated(self, db_conn: AsyncConnection):
        """Insert a row and verify the generated ``day`` column is populated."""
        await db_conn.execute(
            sa.text(
                "INSERT INTO onestop.llm_calls "
                "(purpose, provider, model, status) "
                "VALUES ('eval', 'test', 'test-model', 'ok')"
            )
        )
        result = await db_conn.execute(
            sa.text("SELECT day FROM onestop.llm_calls WHERE provider = 'test'")
        )
        day = result.scalar()
        assert day is not None, "generated day column is NULL"

    async def test_jobs_idempotency_key_unique(self, db_conn: AsyncConnection):
        """Two rows with the same idempotency_key are rejected by the DB."""
        import asyncio  # noqa: PLC0415

        key = "test-idem-key"
        await db_conn.execute(
            sa.text("INSERT INTO onestop.jobs (kind, idempotency_key) VALUES ('test_job', :k)"),
            {"k": key},
        )
        with pytest.raises(Exception, match="unique"):  # noqa: B017
            await db_conn.execute(
                sa.text("INSERT INTO onestop.jobs (kind, idempotency_key) VALUES ('test_job', :k)"),
                {"k": key},
            )
        # Absorb the pending error so teardown can roll back cleanly.
        await asyncio.sleep(0)


@pytest.mark.integration
async def test_upgrade_downgrade_upgrade(test_db_url: str):
    """Full round-trip: upgrade → downgrade → upgrade.

    Exercises the ``downgrade()`` function and confirms the migration can be
    re-applied cleanly (important for the Railway deploy pipeline where
    rolling back may be needed).
    """
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415
    from sqlalchemy import create_engine, pool, text  # noqa: PLC0415

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", test_db_url)

    # We need a fresh database for this test; use a separate schema to isolate.
    # Create a throwaway schema.
    engine = create_engine(test_db_url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS onestop CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.alembic_version"))
        conn.commit()
    engine.dispose()

    command.upgrade(cfg, "head")

    # Verify a key table exists after upgrade.
    engine2 = create_engine(test_db_url, poolclass=pool.NullPool)
    with engine2.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'onestop'")
        )
        count = result.scalar()
    engine2.dispose()
    assert count == 11, f"expected 11 tables after upgrade, got {count}"

    # Downgrade removes all tables.
    command.downgrade(cfg, "base")
    engine3 = create_engine(test_db_url, poolclass=pool.NullPool)
    with engine3.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'onestop'")
        )
        count_after = result.scalar()
    engine3.dispose()
    assert count_after == 0, f"schema should be empty after downgrade, got {count_after}"

    # Re-upgrade: must succeed without errors.
    command.upgrade(cfg, "head")
