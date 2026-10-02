"""Periodic job scheduler backed by the ``schedules`` table (ADR 0003/0004).

``tick`` runs once per poll cycle.  It finds every enabled schedule whose
``next_run_at`` has passed, enqueues one job for it with a deterministic
idempotency key (``<name>:<next_run_at.isoformat()>``), and advances
``next_run_at`` by the schedule's interval.

The idempotency key means that calling ``tick`` twice before the job worker
runs produces only one queued job — the second ``enqueue`` call returns the
existing row's id without inserting a duplicate.

The scheduler itself does not start a background loop; the ``WorkerLoop``
in ``worker.py`` calls ``tick`` during each poll cycle.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.platform.jobs import enqueue
from src.modules.platform.tables import t_schedules

__all__ = ["tick"]


async def tick(conn: AsyncConnection) -> int:
    """Enqueue jobs for all due enabled schedules and advance their clocks.

    Returns the number of schedules processed (0 when nothing was due).

    Args:
        conn: Open ``AsyncConnection`` inside an active transaction.  The
            schedule update and the job enqueue share this transaction so
            that a crash between the two leaves no orphaned or duplicate rows.
    """
    result = await conn.execute(
        sa.select(
            t_schedules.c.name,
            t_schedules.c.interval,
            t_schedules.c.next_run_at,
        )
        .where(t_schedules.c.enabled.is_(True))
        .where(t_schedules.c.next_run_at <= sa.text("now()"))
    )
    rows = result.fetchall()

    for row in rows:
        ikey = f"{row.name}:{row.next_run_at.isoformat()}"
        await enqueue(conn, row.name, {}, idempotency_key=ikey)
        new_next = row.next_run_at + row.interval
        await conn.execute(
            sa.update(t_schedules)
            .where(t_schedules.c.name == row.name)
            .values(next_run_at=new_next, last_run_at=sa.text("now()"))
        )

    return len(rows)
