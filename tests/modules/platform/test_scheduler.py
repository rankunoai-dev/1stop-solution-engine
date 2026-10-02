"""Tests for src.modules.platform.scheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.platform.scheduler import tick
from src.modules.platform.tables import t_jobs, t_schedules

# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestTick:
    def _make_conn(self, rows: list[dict]) -> AsyncMock:
        """Return a mock conn whose first execute() call returns rows."""
        conn = AsyncMock(spec=AsyncConnection)
        # First execute: SELECT due schedules
        select_result = MagicMock()
        mocked_rows = []
        for r in rows:
            m = MagicMock()
            m.name = r["name"]
            m.interval = r["interval"]
            m.next_run_at = r["next_run_at"]
            mocked_rows.append(m)
        select_result.fetchall.return_value = mocked_rows
        # Subsequent executes: enqueue inserts + schedule updates — just succeed
        other_result = MagicMock()
        other_result.scalar_one.return_value = MagicMock()
        conn.execute.side_effect = [select_result] + [other_result] * (len(rows) * 2)
        return conn

    async def test_returns_zero_when_nothing_due(self):
        conn = self._make_conn([])
        count = await tick(conn)
        assert count == 0

    async def test_returns_count_of_due_schedules(self):
        now = datetime.now(UTC)
        rows = [
            {
                "name": "job_a",
                "interval": timedelta(days=1),
                "next_run_at": now - timedelta(minutes=5),
            },
            {
                "name": "job_b",
                "interval": timedelta(days=7),
                "next_run_at": now - timedelta(minutes=1),
            },
        ]
        conn = self._make_conn(rows)
        with patch("src.modules.platform.scheduler.enqueue") as mock_enqueue:
            mock_enqueue.return_value = MagicMock()
            count = await tick(conn)
        assert count == 2

    async def test_uses_idempotency_key(self):
        now = datetime.now(UTC)
        past = now - timedelta(minutes=5)
        rows = [{"name": "weekly_sync", "interval": timedelta(days=7), "next_run_at": past}]
        conn = self._make_conn(rows)
        with patch("src.modules.platform.scheduler.enqueue") as mock_enqueue:
            mock_enqueue.return_value = MagicMock()
            await tick(conn)
        call_kwargs = mock_enqueue.call_args
        assert call_kwargs.kwargs["idempotency_key"] == f"weekly_sync:{past.isoformat()}"

    async def test_enqueues_with_schedule_name_as_kind(self):
        now = datetime.now(UTC)
        rows = [
            {
                "name": "housekeeping",
                "interval": timedelta(days=1),
                "next_run_at": now - timedelta(seconds=1),
            }
        ]
        conn = self._make_conn(rows)
        with patch("src.modules.platform.scheduler.enqueue") as mock_enqueue:
            mock_enqueue.return_value = MagicMock()
            await tick(conn)
        assert mock_enqueue.call_args.args[1] == "housekeeping"


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTickIntegration:
    async def test_tick_enqueues_due_schedule(self, db_conn: AsyncConnection):
        """Insert a schedule that is already due and confirm a job is enqueued."""
        name = "test_schedule_due"
        past = datetime.now(UTC) - timedelta(minutes=5)
        await db_conn.execute(
            sa.insert(t_schedules).values(
                name=name,
                interval=sa.text("'1 day'::interval"),
                next_run_at=past,
                enabled=True,
            )
        )
        count = await tick(db_conn)
        assert count >= 1
        result = await db_conn.execute(sa.select(t_jobs.c.kind).where(t_jobs.c.kind == name))
        assert result.scalar_one() == name

    async def test_tick_advances_next_run_at(self, db_conn: AsyncConnection):
        name = "test_schedule_advance"
        past = datetime.now(UTC) - timedelta(hours=1)
        interval_days = 7
        await db_conn.execute(
            sa.insert(t_schedules).values(
                name=name,
                interval=sa.text(f"'{interval_days} days'::interval"),
                next_run_at=past,
                enabled=True,
            )
        )
        await tick(db_conn)
        result = await db_conn.execute(
            sa.select(t_schedules.c.next_run_at).where(t_schedules.c.name == name)
        )
        new_next = result.scalar_one()
        # next_run_at should have moved forward by ~7 days
        expected = past + timedelta(days=interval_days)
        diff = abs((new_next.replace(tzinfo=UTC) - expected).total_seconds())
        assert diff < 5  # within 5 seconds

    async def test_tick_skips_disabled_schedule(self, db_conn: AsyncConnection):
        name = "test_schedule_disabled"
        past = datetime.now(UTC) - timedelta(minutes=5)
        await db_conn.execute(
            sa.insert(t_schedules).values(
                name=name,
                interval=sa.text("'1 day'::interval"),
                next_run_at=past,
                enabled=False,
            )
        )
        await tick(db_conn)
        # Only counts schedules we just inserted that are due AND enabled.
        # The disabled one must not appear.
        result = await db_conn.execute(
            sa.select(sa.func.count()).select_from(t_jobs).where(t_jobs.c.kind == name)
        )
        assert result.scalar_one() == 0

    async def test_tick_idempotent_double_call(self, db_conn: AsyncConnection):
        """Two tick calls for the same schedule period produce one job."""
        name = "test_schedule_idem"
        past = datetime.now(UTC) - timedelta(hours=2)
        await db_conn.execute(
            sa.insert(t_schedules).values(
                name=name,
                interval=sa.text("'1 day'::interval"),
                next_run_at=past,
                enabled=True,
            )
        )
        # After first tick, next_run_at advances; second tick won't fire again.
        await tick(db_conn)
        await tick(db_conn)
        result = await db_conn.execute(
            sa.select(sa.func.count()).select_from(t_jobs).where(t_jobs.c.kind == name)
        )
        assert result.scalar_one() == 1
