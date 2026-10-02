"""Persisted daily/monthly spend guard backed by the ``llm_calls`` table (ADR 0005).

Design
------
The guard enforces two hard ceilings (day, month) plus a runtime kill switch
stored in ``settings_kv``.  A Postgres advisory lock prevents concurrent
requests from both reading "under budget" and both proceeding, which would let
the actual spend overshoot the cap.

Typical call sequence inside one transaction::

    guard = PersistedSpendGuard.from_settings()
    cost = cost_usd(settings.llm_provider, settings.llm_model, in_tok, est_out)

    async with transaction() as conn:
        await guard.reserve(conn, cost, purpose="answer")
        # --- make the actual LLM call here ---
        await guard.record(conn, purpose="answer", provider=..., model=...,
                           input_tokens=in_tok, output_tokens=actual_out_tok,
                           cost=actual_cost)

``reserve`` acquires ``pg_advisory_xact_lock``, which is held until the
transaction commits or rolls back.  Any concurrent ``reserve`` call blocks at
the lock until the first transaction completes, then re-reads the updated
total — preventing overshoot.

Concurrent overshoot window
---------------------------
There is a small window between ``reserve`` completing (lock released on
commit) and the actual LLM response arriving (the ``record`` call).  During
that window a second request can reserve against the already-committed first
reservation.  For a low-traffic internal tool (<10 concurrent users), the
overshoot is bounded by (max_concurrent - 1) * max_cost_per_call, which is
well within the default cap headroom.  This is documented and acceptable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.modules.platform.settings import OneStopSettings

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.core.errors import BudgetExceededError
from src.modules.platform.tables import t_llm_calls, t_settings_kv

__all__ = ["CapExceededError", "PersistedSpendGuard", "SpendStatus"]

# Fixed advisory lock key for the spend guard.  Any concurrent transaction that
# calls reserve() will block here until the first commits or rolls back.
_LOCK_KEY = 424_242

_KILL_SWITCH_KEY = "llm.kill_switch"

_DAY_TOTAL = sa.text(
    "SELECT COALESCE(SUM(cost_usd), 0)::numeric FROM onestop.llm_calls WHERE day = CURRENT_DATE"
)
_MONTH_TOTAL = sa.text(
    "SELECT COALESCE(SUM(cost_usd), 0)::numeric FROM onestop.llm_calls"
    " WHERE date_trunc('month', day) = date_trunc('month', CURRENT_DATE)"
)


class CapExceededError(BudgetExceededError):
    """A persisted day/month cap or the kill switch prevented an LLM call.

    Subclasses ``BudgetExceededError`` so existing catch clauses continue to
    work; adds ``reason`` so the API layer can return a precise error message.
    """

    def __init__(
        self,
        reason: Literal["day_cap", "month_cap", "kill_switch"],
        attempted_usd: Decimal,
        spent_usd: Decimal,
        ceiling_usd: Decimal,
    ) -> None:
        """Record the reason and the spend figures for the blocked call."""
        self.reason = reason
        super().__init__(float(attempted_usd), float(spent_usd), float(ceiling_usd))


@dataclass(frozen=True)
class SpendStatus:
    """Current spend totals and configured caps."""

    day_usd: Decimal
    month_usd: Decimal
    day_cap_usd: Decimal
    month_cap_usd: Decimal
    kill_switch: bool


class PersistedSpendGuard:
    """Check caps, record LLM calls, and report spend status against ``llm_calls``."""

    def __init__(self, day_cap_usd: Decimal, month_cap_usd: Decimal) -> None:
        """Initialise with explicit cap values (use ``from_settings`` in production)."""
        self._day_cap = day_cap_usd
        self._month_cap = month_cap_usd

    @classmethod
    def from_settings(cls, settings: OneStopSettings | None = None) -> PersistedSpendGuard:
        """Create a guard from ``OneStopSettings`` (reads the process singleton by default)."""
        if settings is None:
            from src.modules.platform.settings import get_onestop_settings  # noqa: PLC0415

            settings = get_onestop_settings()
        return cls(
            day_cap_usd=Decimal(str(settings.spend_cap_day_usd)),
            month_cap_usd=Decimal(str(settings.spend_cap_month_usd)),
        )

    async def reserve(
        self,
        conn: AsyncConnection,
        cost: Decimal,
    ) -> None:
        """Acquire the advisory lock and check all caps.

        Raises ``CapExceededError`` if the kill switch is active or adding
        *cost* to today's or this month's total would exceed the configured
        ceiling.  The lock is held until *conn*'s transaction commits or rolls
        back, preventing concurrent overshoot.

        Args:
            conn: Open ``AsyncConnection`` inside an active transaction.
            cost: Estimated cost of the upcoming LLM call in USD.
        """
        await conn.execute(
            sa.text("SELECT pg_advisory_xact_lock(:k)"),
            {"k": _LOCK_KEY},
        )

        if await _get_kill_switch(conn):
            raise CapExceededError(
                "kill_switch",
                cost,
                Decimal("0"),
                Decimal("0"),
            )

        day_total = await _get_day_total(conn)
        if day_total + cost > self._day_cap:
            raise CapExceededError("day_cap", cost, day_total, self._day_cap)

        month_total = await _get_month_total(conn)
        if month_total + cost > self._month_cap:
            raise CapExceededError("month_cap", cost, month_total, self._month_cap)

    async def record(
        self,
        conn: AsyncConnection,
        *,
        purpose: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: Decimal,
        latency_ms: int | None = None,
        status: str = "ok",
        trace_id: str | None = None,
        conversation_id: uuid.UUID | None = None,
        error: str | None = None,
    ) -> uuid.UUID:
        """Insert a row into ``llm_calls`` and return its id.

        Call this after the LLM call completes, inside the same transaction as
        ``reserve``.  The ``day`` column is ``GENERATED ALWAYS`` in Postgres
        and must not be included in the insert.

        Args:
            conn: Open ``AsyncConnection`` inside an active transaction.
            purpose: One of the purpose values tracked in the schema
                (``"answer"``, ``"judge"``, ``"card_draft"``, etc.).
            provider: Lower-case provider name, e.g. ``"anthropic"``.
            model: Exact model string as passed to the provider API.
            input_tokens: Prompt tokens consumed.
            output_tokens: Completion tokens generated.
            cost: Actual cost in USD (use ``pricing.cost_usd``).
            latency_ms: Round-trip time in milliseconds, if measured.
            status: ``"ok"`` (default) or ``"error"``.
            trace_id: Optional correlation id for distributed tracing.
            conversation_id: UUID of the associated conversation, if any.
            error: Error message when ``status="error"``.
        """
        row_id = uuid.uuid4()
        await conn.execute(
            sa.insert(t_llm_calls).values(
                id=row_id,
                # day is excluded: GENERATED ALWAYS AS (created_at::date) STORED
                purpose=purpose,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
                status=status,
                trace_id=trace_id,
                conversation_id=conversation_id,
                error=error,
            )
        )
        return row_id

    async def status(self, conn: AsyncConnection) -> SpendStatus:
        """Return current day/month totals and cap values.

        Args:
            conn: Open ``AsyncConnection``.  Read-only; no lock is acquired.
        """
        day_total = await _get_day_total(conn)
        month_total = await _get_month_total(conn)
        kill = await _get_kill_switch(conn)
        return SpendStatus(
            day_usd=day_total,
            month_usd=month_total,
            day_cap_usd=self._day_cap,
            month_cap_usd=self._month_cap,
            kill_switch=kill,
        )

    async def set_kill_switch(
        self,
        conn: AsyncConnection,
        enabled: bool,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        """Upsert the kill switch value in ``settings_kv``.

        When enabled, all subsequent ``reserve`` calls raise
        ``CapExceededError("kill_switch", ...)``.

        Args:
            conn: Open ``AsyncConnection`` inside an active transaction.
            enabled: ``True`` to block LLM calls; ``False`` to re-enable them.
            actor_id: UUID of the admin who toggled the switch, for the audit trail.
        """
        await conn.execute(
            pg_insert(t_settings_kv)
            .values(key=_KILL_SWITCH_KEY, value=enabled, updated_by=actor_id)
            .on_conflict_do_update(
                index_elements=["key"],
                set_={
                    "value": enabled,
                    "updated_by": actor_id,
                    "updated_at": sa.text("now()"),
                },
            )
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _get_day_total(conn: AsyncConnection) -> Decimal:
    result = await conn.execute(_DAY_TOTAL)
    return Decimal(str(result.scalar_one()))


async def _get_month_total(conn: AsyncConnection) -> Decimal:
    result = await conn.execute(_MONTH_TOTAL)
    return Decimal(str(result.scalar_one()))


async def _get_kill_switch(conn: AsyncConnection) -> bool:
    result = await conn.execute(
        sa.select(t_settings_kv.c.value).where(t_settings_kv.c.key == _KILL_SWITCH_KEY)
    )
    raw = result.scalar_one_or_none()
    return bool(raw) if raw is not None else False
