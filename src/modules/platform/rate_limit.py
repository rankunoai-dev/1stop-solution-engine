"""Fixed-window rate limiter backed by the ``rate_limits`` table (ARCHITECTURE S5).

A single ``INSERT ... ON CONFLICT DO UPDATE`` atomically increments the counter
for the current window.  No application-side lock is needed; Postgres handles
concurrent upserts on the primary key (``key``, ``window_start``).

Window alignment
----------------
Windows are aligned to the Unix epoch, not to the first request's arrival time.

    window_start = floor(epoch_seconds / window_seconds) * window_seconds

A 60-second window always starts at :00 and :60.  A request at :35 and a
request at :55 are in the same window; a request at :61 is in the next.  This
prevents clock drift from creating overlapping windows.

Increment-then-check semantics
-------------------------------
The counter is incremented **before** the result is checked, even when the
limit is already exceeded.  This is intentional for login-attempt rate
limiting: you want every attempt counted whether or not the code was correct.

Callers that need "check first, only count on success" must read the current
count in a read-only query and call ``check_and_increment`` only if the count
is below the limit.  That pattern is left to the auth module (R0.9).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = ["check_and_increment"]

_UPSERT = sa.text(
    """
    INSERT INTO onestop.rate_limits (key, window_start, count)
    VALUES (
        :key,
        to_timestamp(floor(extract(epoch FROM now()) / :w) * :w),
        1
    )
    ON CONFLICT (key, window_start)
    DO UPDATE SET count = onestop.rate_limits.count + 1
    RETURNING count
    """
)


async def check_and_increment(
    conn: AsyncConnection,
    key: str,
    limit: int,
    window_seconds: int,
) -> bool:
    """Atomically increment the counter for *key* and return whether it is within *limit*.

    Returns ``True`` (allowed) if the post-increment count is <= *limit*,
    ``False`` (blocked) otherwise.

    Args:
        conn: Open ``AsyncConnection``.  The upsert is committed (or rolled
            back) with the surrounding transaction.  For login rate limiting,
            pass a connection that is NOT in a long-running transaction so the
            count is persisted even when the overall login attempt fails.
        key: Namespaced string identifying the resource and principal being
            rate-limited, e.g. ``"login:user@example.com"`` or
            ``"chat:session-<uuid>"``.
        limit: Maximum number of requests permitted within the window
            (inclusive: limit=5 means the 5th request is the last allowed).
        window_seconds: Window length in seconds (e.g. 60, 300, 3600).
    """
    result = await conn.execute(_UPSERT, {"key": key, "w": window_seconds})
    count: int = result.scalar_one()
    return count <= limit
