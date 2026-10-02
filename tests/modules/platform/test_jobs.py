"""Tests for src.modules.platform.jobs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.platform.jobs import (
    ClaimedJob,
    claim,
    clear_handlers,
    complete,
    enqueue,
    fail,
    register,
)
from src.modules.platform.tables import t_jobs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_enqueue_conn(row_id: uuid.UUID) -> AsyncMock:
    conn = AsyncMock(spec=AsyncConnection)
    result = MagicMock()
    result.scalar_one.return_value = row_id
    conn.execute.return_value = result
    return conn


def _make_claim_conn(row: dict[str, Any] | None) -> AsyncMock:
    conn = AsyncMock(spec=AsyncConnection)
    result = MagicMock()
    result.mappings.return_value.fetchone.return_value = row
    conn.execute.return_value = result
    return conn


def _make_fail_conn(attempts: int, max_attempts: int) -> AsyncMock:
    conn = AsyncMock(spec=AsyncConnection)
    read_result = MagicMock()
    read_result.one.return_value = MagicMock(attempts=attempts, max_attempts=max_attempts)
    update_result = MagicMock()
    conn.execute.side_effect = [read_result, update_result]
    return conn


# ---------------------------------------------------------------------------
# Unit tests — enqueue
# ---------------------------------------------------------------------------


class TestEnqueue:
    async def test_returns_uuid(self):
        expected = uuid.uuid4()
        conn = _make_enqueue_conn(expected)
        result = await enqueue(conn, "test_kind")
        assert result == expected

    async def test_calls_execute_once(self):
        conn = _make_enqueue_conn(uuid.uuid4())
        await enqueue(conn, "test_kind")
        conn.execute.assert_awaited_once()

    async def test_returns_uuid_when_idempotency_key_given(self):
        expected = uuid.uuid4()
        conn = _make_enqueue_conn(expected)
        result = await enqueue(conn, "test_kind", idempotency_key="key-abc")
        assert result == expected

    async def test_default_payload_is_empty_dict(self):
        """No payload argument → enqueue succeeds (payload defaults to {})."""
        conn = _make_enqueue_conn(uuid.uuid4())
        await enqueue(conn, "test_kind")
        conn.execute.assert_awaited_once()

    async def test_explicit_payload_is_passed(self):
        conn = _make_enqueue_conn(uuid.uuid4())
        await enqueue(conn, "test_kind", {"answer": 42})
        conn.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# Unit tests — claim
# ---------------------------------------------------------------------------


class TestClaim:
    _row: dict[str, Any] = {
        "id": uuid.uuid4(),
        "kind": "test_kind",
        "payload": {"x": 1},
        "attempts": 1,
        "max_attempts": 3,
    }

    async def test_returns_claimed_job_when_row_exists(self):
        conn = _make_claim_conn(self._row)
        job = await claim(conn, "w1", ["test_kind"])
        assert isinstance(job, ClaimedJob)
        assert job.kind == "test_kind"
        assert job.attempts == 1

    async def test_returns_none_when_no_jobs(self):
        conn = _make_claim_conn(None)
        result = await claim(conn, "w1", ["test_kind"])
        assert result is None

    async def test_payload_defaults_to_empty_dict_on_null(self):
        row = {**self._row, "payload": None}
        conn = _make_claim_conn(row)
        job = await claim(conn, "w1", ["test_kind"])
        assert job is not None
        assert job.payload == {}

    async def test_calls_execute_once(self):
        conn = _make_claim_conn(None)
        await claim(conn, "w1", ["test_kind"])
        conn.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# Unit tests — complete
# ---------------------------------------------------------------------------


class TestComplete:
    async def test_calls_execute_once(self):
        conn = AsyncMock(spec=AsyncConnection)
        conn.execute.return_value = MagicMock()
        await complete(conn, uuid.uuid4())
        conn.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# Unit tests — fail
# ---------------------------------------------------------------------------


class TestFail:
    async def test_sets_dead_at_max_attempts(self):
        conn = _make_fail_conn(attempts=3, max_attempts=3)
        await fail(conn, uuid.uuid4(), "boom")
        # "dead" path: no backoff_s key in params, SQL text contains "dead"
        update_sql = conn.execute.call_args_list[1].args[0].text
        assert "dead" in update_sql

    async def test_sets_failed_when_retries_remain(self):
        conn = _make_fail_conn(attempts=1, max_attempts=3)
        await fail(conn, uuid.uuid4(), "boom")
        # "failed" path: backoff_s is present in params, SQL text contains "failed"
        update_params = conn.execute.call_args_list[1].args[1]
        assert "backoff_s" in update_params

    async def test_two_execute_calls(self):
        conn = _make_fail_conn(attempts=1, max_attempts=3)
        await fail(conn, uuid.uuid4(), "boom")
        assert conn.execute.call_count == 2


# ---------------------------------------------------------------------------
# Unit tests — handler registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def setup_method(self) -> None:
        clear_handlers()

    def teardown_method(self) -> None:
        clear_handlers()

    def test_register_and_retrieve(self):
        from src.modules.platform.jobs import _HANDLERS  # noqa: PLC0415

        async def my_handler(job: ClaimedJob) -> None:
            pass

        register("my_kind", my_handler)
        assert _HANDLERS["my_kind"] is my_handler

    def test_clear_removes_all(self):
        from src.modules.platform.jobs import _HANDLERS  # noqa: PLC0415

        async def h(job: ClaimedJob) -> None:
            pass

        register("k1", h)
        register("k2", h)
        clear_handlers()
        assert len(_HANDLERS) == 0


# ---------------------------------------------------------------------------
# Integration tests (require docker compose up -d db)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestJobsIntegration:
    async def test_enqueue_inserts_row(self, db_conn: AsyncConnection):
        job_id = await enqueue(db_conn, "test.enqueue", {"n": 1})
        result = await db_conn.execute(sa.select(t_jobs.c.kind).where(t_jobs.c.id == job_id))
        assert result.scalar_one() == "test.enqueue"

    async def test_claim_returns_job(self, db_conn: AsyncConnection):
        await enqueue(db_conn, "test.claim", {"v": 42})
        job = await claim(db_conn, "test-worker", ["test.claim"])
        assert job is not None
        assert job.kind == "test.claim"
        assert job.payload == {"v": 42}

    async def test_claim_returns_none_when_empty(self, db_conn: AsyncConnection):
        result = await claim(db_conn, "test-worker", ["no.such.kind"])
        assert result is None

    async def test_complete_sets_succeeded(self, db_conn: AsyncConnection):
        job_id = await enqueue(db_conn, "test.complete")
        job = await claim(db_conn, "test-worker", ["test.complete"])
        assert job is not None
        await complete(db_conn, job.id)
        result = await db_conn.execute(sa.select(t_jobs.c.status).where(t_jobs.c.id == job_id))
        assert result.scalar_one() == "succeeded"

    async def test_fail_sets_failed_with_retries_remaining(self, db_conn: AsyncConnection):
        job_id = await enqueue(db_conn, "test.fail")
        job = await claim(db_conn, "test-worker", ["test.fail"])
        assert job is not None
        await fail(db_conn, job.id, "oops")
        result = await db_conn.execute(
            sa.select(t_jobs.c.status, t_jobs.c.last_error).where(t_jobs.c.id == job_id)
        )
        row = result.one()
        assert row.status == "failed"
        assert row.last_error == "oops"

    async def test_fail_sets_dead_at_max_attempts(self, db_conn: AsyncConnection):
        job_id = await enqueue(db_conn, "test.dead")
        # Claim 3 times (max_attempts=3, each claim increments attempts).
        for _ in range(3):
            job = await claim(db_conn, "test-worker", ["test.dead"])
            if job is not None:
                await fail(db_conn, job.id, "boom")
        result = await db_conn.execute(sa.select(t_jobs.c.status).where(t_jobs.c.id == job_id))
        assert result.scalar_one() == "dead"

    async def test_idempotent_enqueue_returns_existing_id(self, db_conn: AsyncConnection):
        key = "idem-key-1"
        id1 = await enqueue(db_conn, "test.idem", idempotency_key=key)
        id2 = await enqueue(db_conn, "test.idem", idempotency_key=key)
        assert id1 == id2

    async def test_idempotent_enqueue_creates_one_row(self, db_conn: AsyncConnection):
        key = "idem-key-2"
        await enqueue(db_conn, "test.idem", idempotency_key=key)
        await enqueue(db_conn, "test.idem", idempotency_key=key)
        result = await db_conn.execute(
            sa.select(sa.func.count()).where(t_jobs.c.idempotency_key == key)
        )
        assert result.scalar_one() == 1

    async def test_claim_respects_run_after(self, db_conn: AsyncConnection):
        future = datetime.now(UTC) + timedelta(hours=1)
        await enqueue(db_conn, "test.future", run_after=future)
        job = await claim(db_conn, "test-worker", ["test.future"])
        assert job is None

    async def test_attempts_incremented_on_claim(self, db_conn: AsyncConnection):
        job_id = await enqueue(db_conn, "test.attempts")
        job = await claim(db_conn, "test-worker", ["test.attempts"])
        assert job is not None
        assert job.attempts == 1
        result = await db_conn.execute(sa.select(t_jobs.c.attempts).where(t_jobs.c.id == job_id))
        assert result.scalar_one() == 1
