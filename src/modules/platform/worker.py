"""Async worker loop: claims jobs, dispatches to handlers, runs the scheduler (R0.7).

Usage (in the FastAPI lifespan or a standalone process)::

    from src.modules.platform.jobs import register
    from src.modules.platform.worker import WorkerLoop

    register("weekly_sync", my_sync_handler)
    register("housekeeping", my_housekeeping_handler)

    loop = WorkerLoop(kinds=["weekly_sync", "housekeeping"])
    asyncio.create_task(loop.run_until_stopped())
    # ... later, on shutdown:
    loop.stop()

Design notes
------------
- Each ``run_once`` call opens its own transaction.  The claim, handler
  execution, and status update (complete/fail) all commit together.
- If the process is killed mid-job the transaction rolls back, and the job
  returns to its previous status.  The stale-lock timeout in ``claim``
  recovers it on the next poll.
- ``WorkerLoop`` accepts an ``engine`` for test injection.  In production
  it calls ``get_engine()`` on each iteration so the engine is never held
  across a restart.
"""

from __future__ import annotations

import asyncio
import uuid as _uuid

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from src.modules.platform.jobs import (
    _HANDLERS,
    ClaimedJob,
    claim,
    complete,
    fail,
)
from src.modules.platform.scheduler import tick

__all__ = ["WorkerLoop"]


class WorkerLoop:
    """Poll for jobs, dispatch to handlers, and run the scheduler."""

    def __init__(
        self,
        kinds: list[str],
        poll_interval_s: float = 2.0,
        lock_expiry_s: int = 30,
        *,
        run_scheduler: bool = True,
        engine: AsyncEngine | None = None,
    ) -> None:
        """Configure the worker.

        Args:
            kinds: Job kinds this worker handles.
            poll_interval_s: Seconds to wait between polls when the queue
                is empty.
            lock_expiry_s: Seconds before a ``running`` job's lock is
                considered stale and re-claimable.
            run_scheduler: When ``True``, call ``scheduler.tick`` on each
                poll cycle before trying to claim a job.
            engine: Inject an ``AsyncEngine`` for tests; if ``None``, the
                production engine from ``get_engine()`` is used.
        """
        self._kinds = kinds
        self._poll_interval_s = poll_interval_s
        self._lock_expiry_s = lock_expiry_s
        self._run_scheduler = run_scheduler
        self._engine = engine
        self._worker_id = f"worker:{_uuid.uuid4()}"
        self._running = False

    async def run_once(self) -> bool:
        """Claim and execute one job; also tick the scheduler if enabled.

        Returns ``True`` if a job was processed, ``False`` if the queue
        was empty.
        """
        from src.modules.platform.db import get_engine  # noqa: PLC0415

        engine = self._engine if self._engine is not None else get_engine()
        async with engine.begin() as conn:
            if self._run_scheduler:
                await tick(conn)
            job = await claim(conn, self._worker_id, self._kinds, lock_expiry_s=self._lock_expiry_s)
            if job is None:
                return False
            await self._dispatch(conn, job)
        return True

    async def _dispatch(self, conn: AsyncConnection, job: ClaimedJob) -> None:
        handler = _HANDLERS.get(job.kind)
        if handler is None:
            await fail(conn, job.id, f"No handler registered for kind '{job.kind}'")
            return
        try:
            await handler(job)
            await complete(conn, job.id)
        except Exception as exc:  # noqa: BLE001
            await fail(conn, job.id, str(exc))

    async def run_until_stopped(self) -> None:
        """Poll and dispatch indefinitely until ``stop()`` is called."""
        self._running = True
        while self._running:
            processed = await self.run_once()
            if not processed:
                await asyncio.sleep(self._poll_interval_s)

    def stop(self) -> None:
        """Signal the loop to exit after the current iteration completes."""
        self._running = False
