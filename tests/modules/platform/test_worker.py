"""Tests for src.modules.platform.worker."""

from __future__ import annotations

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.modules.platform.jobs import (
    ClaimedJob,
    clear_handlers,
    register,
)
from src.modules.platform.tables import t_jobs
from src.modules.platform.worker import WorkerLoop

# ---------------------------------------------------------------------------
# Unit tests (no database — behaviour tested via integration below)
# ---------------------------------------------------------------------------


class TestWorkerLoopUnit:
    def test_stop_sets_running_false(self):
        loop = WorkerLoop(["test.kind"])
        loop._running = True
        loop.stop()
        assert loop._running is False

    def test_worker_id_is_unique(self):
        w1 = WorkerLoop(["k"])
        w2 = WorkerLoop(["k"])
        assert w1._worker_id != w2._worker_id

    async def test_run_until_stopped_exits_after_stop(self):
        """run_until_stopped returns when stop() is called from a task."""

        async def _stopper(wl: WorkerLoop) -> None:
            await asyncio.sleep(0.05)
            wl.stop()

        loop = WorkerLoop(["no.such.kind"], poll_interval_s=0.01, run_scheduler=False)
        # Point at a no-op engine so no real DB is needed.
        from unittest.mock import AsyncMock, MagicMock  # noqa: PLC0415

        mock_engine = MagicMock()
        conn = AsyncMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        # run_scheduler=False so only claim() fires per iteration.
        # claim returns None → run_once returns False → sleep → repeat.
        claim_result = MagicMock()
        claim_result.mappings.return_value.fetchone.return_value = None
        conn.execute.return_value = claim_result
        mock_engine.begin.return_value = conn
        loop._engine = mock_engine

        await asyncio.gather(
            loop.run_until_stopped(),
            _stopper(loop),
        )
        assert not loop._running


# ---------------------------------------------------------------------------
# Integration tests (require docker compose up -d db)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestWorkerLoopIntegration:
    def setup_method(self) -> None:
        clear_handlers()

    def teardown_method(self) -> None:
        clear_handlers()

    async def test_run_once_processes_job(self, test_engine: AsyncEngine):
        job_id = uuid.uuid4()
        async with test_engine.begin() as conn:
            await conn.execute(
                sa.insert(t_jobs).values(id=job_id, kind="test.worker.ok", payload={})
            )

        called: list[ClaimedJob] = []

        async def handler(job: ClaimedJob) -> None:
            called.append(job)

        register("test.worker.ok", handler)
        loop = WorkerLoop(["test.worker.ok"], run_scheduler=False, engine=test_engine)
        result = await loop.run_once()

        assert result is True
        assert len(called) == 1
        assert called[0].id == job_id

        async with test_engine.connect() as conn:
            r = await conn.execute(sa.select(t_jobs.c.status).where(t_jobs.c.id == job_id))
            assert r.scalar_one() == "succeeded"

        # Cleanup
        async with test_engine.begin() as conn:
            await conn.execute(sa.delete(t_jobs).where(t_jobs.c.id == job_id))

    async def test_run_once_fails_job_on_handler_error(self, test_engine: AsyncEngine):
        job_id = uuid.uuid4()
        async with test_engine.begin() as conn:
            await conn.execute(
                sa.insert(t_jobs).values(id=job_id, kind="test.worker.fail", payload={})
            )

        async def bad_handler(job: ClaimedJob) -> None:
            msg = "intentional test error"
            raise RuntimeError(msg)

        register("test.worker.fail", bad_handler)
        loop = WorkerLoop(["test.worker.fail"], run_scheduler=False, engine=test_engine)
        result = await loop.run_once()

        assert result is True

        async with test_engine.connect() as conn:
            r = await conn.execute(
                sa.select(t_jobs.c.status, t_jobs.c.last_error).where(t_jobs.c.id == job_id)
            )
            row = r.one()
            assert row.status == "failed"
            assert "intentional test error" in row.last_error

        async with test_engine.begin() as conn:
            await conn.execute(sa.delete(t_jobs).where(t_jobs.c.id == job_id))

    async def test_run_once_returns_false_when_empty(self, test_engine: AsyncEngine):
        loop = WorkerLoop(["test.worker.empty"], run_scheduler=False, engine=test_engine)
        result = await loop.run_once()
        assert result is False

    async def test_skip_locked_two_workers_no_double_claim(self, test_engine: AsyncEngine):
        """Two concurrent workers must claim different jobs."""
        ids = [uuid.uuid4(), uuid.uuid4()]
        async with test_engine.begin() as conn:
            for jid in ids:
                await conn.execute(
                    sa.insert(t_jobs).values(id=jid, kind="test.worker.skip", payload={})
                )

        seen: list[uuid.UUID] = []

        async def handler(job: ClaimedJob) -> None:
            seen.append(job.id)

        register("test.worker.skip", handler)
        w1 = WorkerLoop(["test.worker.skip"], run_scheduler=False, engine=test_engine)
        w2 = WorkerLoop(["test.worker.skip"], run_scheduler=False, engine=test_engine)

        await asyncio.gather(w1.run_once(), w2.run_once())

        # Both jobs processed, no duplicates.
        assert len(seen) == 2
        assert seen[0] != seen[1]

        async with test_engine.begin() as conn:
            await conn.execute(sa.delete(t_jobs).where(t_jobs.c.id.in_(ids)))
