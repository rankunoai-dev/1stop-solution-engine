"""Async job queue backed by the ``jobs`` table (D-19, ADR 0003).

The queue uses ``FOR UPDATE SKIP LOCKED`` so multiple workers never run the
same job.  One worker claims a job by atomically setting its status to
``running`` and recording its worker ID and timestamp.

Status flow
-----------
::

    queued/failed ──▶ running ──▶ succeeded
                          │
                          └──▶ failed  (attempts < max_attempts; re-runs after backoff)
                          └──▶ dead    (attempts >= max_attempts; terminal)

Stale lock recovery
-------------------
If a worker crashes mid-job the transaction rolls back, putting the job back
to its previous status (``queued`` or ``failed``).  This is the safe path.
For the rarer case where a worker is killed between committing the claim and
committing the result, ``claim`` also picks up ``running`` jobs whose
``locked_at`` is older than *lock_expiry_s*, incrementing ``attempts`` and
resetting ``locked_by``.

Handler registry
----------------
Application modules call ``register(kind, handler_fn)`` at startup.
``WorkerLoop`` dispatches to the registered function for each claimed job.
``clear_handlers()`` is provided for test isolation.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.platform.tables import t_jobs

__all__ = [
    "AsyncHandlerFn",
    "ClaimedJob",
    "claim",
    "clear_handlers",
    "complete",
    "enqueue",
    "fail",
    "register",
]

_BACKOFF_BASE_S: int = 60
_BACKOFF_MAX_S: int = 86_400  # 24 hours


@dataclass
class ClaimedJob:
    """A job that has been atomically claimed by a worker."""

    id: uuid.UUID
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


AsyncHandlerFn = Callable[[ClaimedJob], Awaitable[None]]

_HANDLERS: dict[str, AsyncHandlerFn] = {}

# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------


def register(kind: str, handler: AsyncHandlerFn) -> None:
    """Register *handler* as the executor for jobs of *kind*."""
    _HANDLERS[kind] = handler


def clear_handlers() -> None:
    """Remove all registered handlers. For test isolation only."""
    _HANDLERS.clear()


# ---------------------------------------------------------------------------
# Queue operations
# ---------------------------------------------------------------------------

_CLAIM_SQL = sa.text(
    """
    WITH claimed AS (
        SELECT id
        FROM onestop.jobs
        WHERE (
            (status IN ('queued', 'failed') AND run_after <= now())
            OR (status = 'running'
                AND locked_at + (:lock_s * INTERVAL '1 second') < now())
        )
        AND kind = ANY(:kinds)
        ORDER BY run_after
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    UPDATE onestop.jobs j
    SET status    = 'running',
        locked_by = :worker_id,
        locked_at = now(),
        attempts  = attempts + 1
    FROM claimed
    WHERE j.id = claimed.id
    RETURNING j.id, j.kind, j.payload, j.attempts, j.max_attempts
    """
)


async def enqueue(
    conn: AsyncConnection,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    idempotency_key: str | None = None,
    run_after: datetime | None = None,
) -> uuid.UUID:
    """Insert a job row and return its id.

    When *idempotency_key* is supplied and a row with that key already
    exists, the existing row's id is returned unchanged (no duplicate).

    Args:
        conn: Open ``AsyncConnection`` inside an active transaction.
        kind: Job kind string, e.g. ``"weekly_sync"`` or ``"ingest_tool"``.
        payload: Arbitrary JSON-serialisable data for the handler.
        idempotency_key: Unique key to prevent double-enqueue.
        run_after: Earliest time the job may run.  Defaults to ``now()``.
    """
    effective_payload: dict[str, Any] = payload if payload is not None else {}
    row_id = uuid.uuid4()
    stmt = pg_insert(t_jobs).values(
        id=row_id,
        kind=kind,
        payload=effective_payload,
        idempotency_key=idempotency_key,
        run_after=run_after if run_after is not None else datetime.now(UTC),
    )
    if idempotency_key is not None:
        # On conflict, keep the existing row unchanged and return its id.
        stmt = stmt.on_conflict_do_update(
            index_elements=["idempotency_key"],
            set_={"idempotency_key": t_jobs.c.idempotency_key},
        )
    result = await conn.execute(stmt.returning(t_jobs.c.id))
    return uuid.UUID(str(result.scalar_one()))


async def claim(
    conn: AsyncConnection,
    worker_id: str,
    kinds: list[str],
    *,
    lock_expiry_s: int = 30,
) -> ClaimedJob | None:
    """Atomically claim one pending job for *worker_id*.

    Picks up ``queued``/``failed`` jobs whose ``run_after`` has passed, and
    also stale ``running`` jobs whose lock has expired.  Returns ``None``
    when no matching job is available.

    Args:
        conn: Open ``AsyncConnection`` inside an active transaction.
        worker_id: Unique string identifying this worker instance.
        kinds: Job kinds this worker handles.
        lock_expiry_s: Seconds before a ``running`` job's lock is considered
            stale and can be re-claimed.
    """
    result = await conn.execute(
        _CLAIM_SQL,
        {"lock_s": lock_expiry_s, "kinds": kinds, "worker_id": worker_id},
    )
    row = result.mappings().fetchone()
    if row is None:
        return None
    return ClaimedJob(
        id=row["id"],
        kind=row["kind"],
        payload=dict(row["payload"]) if row["payload"] else {},
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
    )


async def complete(conn: AsyncConnection, job_id: uuid.UUID) -> None:
    """Mark *job_id* as ``succeeded``.

    Args:
        conn: Open ``AsyncConnection`` inside an active transaction.
        job_id: UUID of the job returned by ``claim``.
    """
    await conn.execute(
        sa.update(t_jobs)
        .where(t_jobs.c.id == job_id)
        .values(status="succeeded", finished_at=sa.text("now()"))
    )


async def fail(
    conn: AsyncConnection,
    job_id: uuid.UUID,
    error: str,
) -> None:
    """Record a failed attempt for *job_id*.

    If attempts remain, sets status to ``failed`` and schedules a retry
    with exponential backoff.  When all attempts are exhausted, sets
    status to ``dead``.

    Args:
        conn: Open ``AsyncConnection`` inside an active transaction.
        job_id: UUID of the job returned by ``claim``.
        error: Human-readable error description stored in ``last_error``.
    """
    result = await conn.execute(
        sa.select(t_jobs.c.attempts, t_jobs.c.max_attempts).where(t_jobs.c.id == job_id)
    )
    row = result.one()
    if row.attempts >= row.max_attempts:
        await conn.execute(
            sa.text(
                "UPDATE onestop.jobs"
                " SET status='dead', last_error=:error, finished_at=now()"
                " WHERE id=:id"
            ),
            {"error": error, "id": job_id},
        )
    else:
        backoff_s = min(_BACKOFF_BASE_S * (2 ** (row.attempts - 1)), _BACKOFF_MAX_S)
        await conn.execute(
            sa.text(
                "UPDATE onestop.jobs"
                " SET status='failed', last_error=:error,"
                "     run_after=now() + (:backoff_s * INTERVAL '1 second')"
                " WHERE id=:id"
            ),
            {"error": error, "id": job_id, "backoff_s": backoff_s},
        )
