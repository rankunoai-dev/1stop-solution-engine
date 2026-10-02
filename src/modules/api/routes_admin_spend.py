"""Admin spend-observability routes (R0.11, ARCHITECTURE D-22).

Endpoints
---------
GET /api/v1/admin/spend
    Per-day call totals from ``llm_calls`` for the last *days* days, plus the
    current ``PersistedSpendGuard`` status (totals, caps, kill switch).

POST /api/v1/admin/spend/kill-switch
    Toggle the LLM kill switch on or off.  The guard blocks all subsequent
    ``AnswerLLMTool.execute`` calls while the switch is enabled.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.api.deps import get_db_conn, require_admin, verify_csrf
from src.modules.platform.auth import UserRow
from src.modules.platform.spend import PersistedSpendGuard

__all__ = ["router_admin_spend"]

router_admin_spend = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_SPEND_BY_DAY_SQL = sa.text(
    """
    SELECT
        day,
        purpose,
        COUNT(*) AS call_count,
        SUM(input_tokens) AS input_tokens,
        SUM(output_tokens) AS output_tokens,
        CAST(SUM(cost_usd) AS FLOAT) AS cost_usd
    FROM onestop.llm_calls
    WHERE day >= CURRENT_DATE - (:days)::int * INTERVAL '1 day'
    GROUP BY day, purpose
    ORDER BY day DESC, purpose
    """
)


class KillSwitchBody(BaseModel):
    """Body for POST /admin/spend/kill-switch."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool


@router_admin_spend.get("/spend")
async def get_spend(
    days: int = Query(default=7, ge=1, le=90),
    admin: UserRow = Depends(require_admin),
    conn: AsyncConnection = Depends(get_db_conn),
) -> dict[str, Any]:
    """Return per-day LLM spend totals and the current guard status.

    Args:
        days: Number of past days to include (1–90).
        admin: Requires admin role; injected via ``require_admin``.
        conn: Database connection.

    Returns:
        A dict with ``rows`` (list of per-day aggregates) and ``guard``
        (current day/month totals, caps, and kill-switch state).
    """
    _ = admin
    result = await conn.execute(_SPEND_BY_DAY_SQL, {"days": days})
    rows = [
        {
            "day": str(row["day"]),
            "purpose": row["purpose"],
            "call_count": int(row["call_count"]),
            "input_tokens": int(row["input_tokens"]),
            "output_tokens": int(row["output_tokens"]),
            "cost_usd": float(row["cost_usd"]),
        }
        for row in result.mappings().fetchall()
    ]

    guard = PersistedSpendGuard.from_settings()
    status = await guard.status(conn)

    return {
        "rows": rows,
        "guard": {
            "day_spent_usd": float(status.day_usd),
            "month_spent_usd": float(status.month_usd),
            "day_cap_usd": float(status.day_cap_usd),
            "month_cap_usd": float(status.month_cap_usd),
            "kill_switch": status.kill_switch,
        },
    }


@router_admin_spend.post("/spend/kill-switch")
async def set_kill_switch(
    body: KillSwitchBody,
    admin: UserRow = Depends(require_admin),
    _csrf: None = Depends(verify_csrf),
    conn: AsyncConnection = Depends(get_db_conn),
) -> dict[str, bool]:
    """Enable or disable the LLM kill switch.

    When enabled, all subsequent ``AnswerLLMTool.execute`` calls raise
    ``CapExceededError`` with ``reason="kill_switch"`` until the switch is
    disabled again.

    Args:
        body: ``{"enabled": true/false}``
        admin: Requires admin role; also provides the actor id for auditing.
        _csrf: CSRF validation side-effect.
        conn: Database connection inside an active transaction.

    Returns:
        ``{"kill_switch": <new state>}``
    """
    guard = PersistedSpendGuard.from_settings()
    await guard.set_kill_switch(conn, body.enabled, actor_id=admin.id)
    return {"kill_switch": body.enabled}
