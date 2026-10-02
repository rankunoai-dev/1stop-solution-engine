"""Append-only audit logger (ARCHITECTURE S10).

Every consequential action in the platform writes a row here: logins, cap
changes, sync events, quarantine decisions, admin actions.  The table uses
``GENERATED ALWAYS AS IDENTITY`` so rows are always in strict insertion order
regardless of clock skew.

Usage::

    from src.modules.platform.audit import record

    async with transaction() as conn:
        await conn.execute(sa.insert(t_sessions).values(...))
        await record(conn, action="session.created", target=f"session:{session_id}")
        # Both writes commit together.

The ``record`` call is intentionally inside the caller's transaction so that
the audit row lives and dies with the action it records.  For fire-and-forget
logging that survives a rollback, open a separate ``transaction()`` context.
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.platform.tables import t_audit_log

__all__ = ["record"]


async def record(
    conn: AsyncConnection,
    *,
    action: str,
    target: str,
    actor_user_id: _uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Insert one audit row within *conn*'s transaction.

    Args:
        conn: Open ``AsyncConnection``.  The insert is committed (or rolled
            back) with the surrounding transaction.
        action: Dot-namespaced event name, e.g. ``"login.code_verified"`` or
            ``"spend_cap.updated"``.  Use lowercase with dots; no spaces.
        target: The primary resource this action affected, e.g.
            ``"user:<uuid>"`` or ``"tool:<slug>"``.  Used for filtering.
        actor_user_id: UUID of the staff member who triggered the action, or
            ``None`` for system-initiated events (scheduled jobs, etc.).
        detail: Any additional structured context (IP address, old vs new
            values, etc.).  Stored as JSONB; defaults to ``{}``.
    """
    await conn.execute(
        sa.insert(t_audit_log).values(
            actor_user_id=actor_user_id,
            action=action,
            target=target,
            detail=detail if detail is not None else {},
        )
    )
