"""Tests for src.modules.platform.spend."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.core.errors import BudgetExceededError
from src.modules.platform.spend import (
    CapExceededError,
    PersistedSpendGuard,
    SpendStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DAY_CAP = Decimal("1.00")
_MONTH_CAP = Decimal("10.00")


def _guard(
    day_cap: Decimal = _DAY_CAP,
    month_cap: Decimal = _MONTH_CAP,
) -> PersistedSpendGuard:
    return PersistedSpendGuard(day_cap_usd=day_cap, month_cap_usd=month_cap)


def _make_reserve_conn(
    kill_switch: bool | None = None,
    day_total: Decimal = Decimal("0"),
    month_total: Decimal = Decimal("0"),
) -> AsyncMock:
    """Mock conn with side_effect for the 4 execute calls in reserve()."""
    conn = AsyncMock(spec=AsyncConnection)

    advisory = MagicMock()

    kill_result = MagicMock()
    kill_result.scalar_one_or_none.return_value = kill_switch

    day_result = MagicMock()
    day_result.scalar_one.return_value = day_total

    month_result = MagicMock()
    month_result.scalar_one.return_value = month_total

    conn.execute.side_effect = [advisory, kill_result, day_result, month_result]
    return conn


def _make_status_conn(
    day_total: Decimal = Decimal("0"),
    month_total: Decimal = Decimal("0"),
    kill_switch: bool | None = None,
) -> AsyncMock:
    """Mock conn for the 3 execute calls in status()."""
    conn = AsyncMock(spec=AsyncConnection)

    day_result = MagicMock()
    day_result.scalar_one.return_value = day_total

    month_result = MagicMock()
    month_result.scalar_one.return_value = month_total

    kill_result = MagicMock()
    kill_result.scalar_one_or_none.return_value = kill_switch

    conn.execute.side_effect = [day_result, month_result, kill_result]
    return conn


# ---------------------------------------------------------------------------
# Unit tests — CapExceededError
# ---------------------------------------------------------------------------


class TestCapExceededError:
    def test_inherits_budget_exceeded_error(self):
        err = CapExceededError("day_cap", Decimal("0.10"), Decimal("0.95"), Decimal("1.00"))
        assert isinstance(err, BudgetExceededError)

    def test_reason_stored(self):
        err = CapExceededError("month_cap", Decimal("0.10"), Decimal("9.95"), Decimal("10.00"))
        assert err.reason == "month_cap"

    def test_kill_switch_reason(self):
        err = CapExceededError("kill_switch", Decimal("0.05"), Decimal("0"), Decimal("0"))
        assert err.reason == "kill_switch"

    def test_float_fields_set(self):
        err = CapExceededError("day_cap", Decimal("0.10"), Decimal("0.95"), Decimal("1.00"))
        assert err.attempted_usd == pytest.approx(0.10)
        assert err.spent_usd == pytest.approx(0.95)
        assert err.ceiling_usd == pytest.approx(1.00)


# ---------------------------------------------------------------------------
# Unit tests — PersistedSpendGuard.reserve
# ---------------------------------------------------------------------------


class TestReserve:
    async def test_allowed_when_under_caps(self):
        conn = _make_reserve_conn(day_total=Decimal("0.50"), month_total=Decimal("5.00"))
        await _guard().reserve(conn, Decimal("0.10"))
        # No exception raised

    async def test_acquires_advisory_lock(self):
        conn = _make_reserve_conn()
        await _guard().reserve(conn, Decimal("0.01"))
        # First execute call must pass the lock key as the params dict.
        first_call = conn.execute.call_args_list[0]
        assert first_call.args[1] == {"k": 424_242}

    async def test_raises_day_cap_exceeded(self):
        conn = _make_reserve_conn(day_total=Decimal("0.95"))
        with pytest.raises(CapExceededError) as exc_info:
            await _guard().reserve(conn, Decimal("0.10"))
        assert exc_info.value.reason == "day_cap"

    async def test_raises_month_cap_exceeded(self):
        conn = _make_reserve_conn(day_total=Decimal("0.10"), month_total=Decimal("9.95"))
        with pytest.raises(CapExceededError) as exc_info:
            await _guard().reserve(conn, Decimal("0.10"))
        assert exc_info.value.reason == "month_cap"

    async def test_raises_kill_switch(self):
        conn = _make_reserve_conn(kill_switch=True)
        with pytest.raises(CapExceededError) as exc_info:
            await _guard().reserve(conn, Decimal("0.01"))
        assert exc_info.value.reason == "kill_switch"

    async def test_kill_switch_checked_before_totals(self):
        """Kill switch must block even when spend is zero (lock + switch only)."""
        conn = _make_reserve_conn(kill_switch=True)
        with pytest.raises(CapExceededError) as exc_info:
            await _guard().reserve(conn, Decimal("0"))
        assert exc_info.value.reason == "kill_switch"
        # Only advisory + kill switch queries fired; day/month queries skipped.
        assert conn.execute.call_count == 2

    async def test_exact_day_cap_is_allowed(self):
        """Spending exactly to the cap is allowed; it's exceeding it that blocks."""
        conn = _make_reserve_conn(day_total=Decimal("0.90"))
        await _guard().reserve(conn, Decimal("0.10"))

    async def test_one_cent_over_day_cap_is_blocked(self):
        conn = _make_reserve_conn(day_total=Decimal("0.991"))
        with pytest.raises(CapExceededError) as exc_info:
            await _guard().reserve(conn, Decimal("0.01"))
        assert exc_info.value.reason == "day_cap"


# ---------------------------------------------------------------------------
# Unit tests — PersistedSpendGuard.record
# ---------------------------------------------------------------------------


class TestRecord:
    async def test_returns_uuid(self):
        conn = AsyncMock(spec=AsyncConnection)
        conn.execute.return_value = MagicMock()
        result = await _guard().record(
            conn,
            purpose="answer",
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
            cost=Decimal("0.001"),
        )
        assert isinstance(result, uuid.UUID)

    async def test_calls_execute_once(self):
        conn = AsyncMock(spec=AsyncConnection)
        conn.execute.return_value = MagicMock()
        await _guard().record(
            conn,
            purpose="judge",
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            input_tokens=200,
            output_tokens=80,
            cost=Decimal("0.002"),
        )
        conn.execute.assert_awaited_once()

    async def test_each_call_returns_different_uuid(self):
        conn = AsyncMock(spec=AsyncConnection)
        conn.execute.return_value = MagicMock()
        g = _guard()
        id1 = await g.record(
            conn,
            purpose="answer",
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            input_tokens=10,
            output_tokens=10,
            cost=Decimal("0"),
        )
        conn.execute.return_value = MagicMock()
        id2 = await g.record(
            conn,
            purpose="answer",
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            input_tokens=10,
            output_tokens=10,
            cost=Decimal("0"),
        )
        assert id1 != id2


# ---------------------------------------------------------------------------
# Unit tests — PersistedSpendGuard.status
# ---------------------------------------------------------------------------


class TestStatus:
    async def test_returns_spend_status(self):
        conn = _make_status_conn(day_total=Decimal("0.30"), month_total=Decimal("3.00"))
        result = await _guard().status(conn)
        assert isinstance(result, SpendStatus)

    async def test_totals_match_db_values(self):
        conn = _make_status_conn(day_total=Decimal("0.42"), month_total=Decimal("4.20"))
        result = await _guard().status(conn)
        assert result.day_usd == Decimal("0.42")
        assert result.month_usd == Decimal("4.20")

    async def test_caps_come_from_guard(self):
        conn = _make_status_conn()
        result = await _guard(day_cap=Decimal("2.00"), month_cap=Decimal("20.00")).status(conn)
        assert result.day_cap_usd == Decimal("2.00")
        assert result.month_cap_usd == Decimal("20.00")

    async def test_kill_switch_false_when_not_set(self):
        conn = _make_status_conn(kill_switch=None)
        result = await _guard().status(conn)
        assert result.kill_switch is False

    async def test_kill_switch_true_when_set(self):
        conn = _make_status_conn(kill_switch=True)
        result = await _guard().status(conn)
        assert result.kill_switch is True


# ---------------------------------------------------------------------------
# Integration tests (require docker compose up -d db)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPersistedSpendGuardIntegration:
    async def test_reserve_and_record_round_trip(self, db_conn: AsyncConnection):
        guard = PersistedSpendGuard(Decimal("5.00"), Decimal("50.00"))
        cost = Decimal("0.001")
        await guard.reserve(db_conn, cost)
        row_id = await guard.record(
            db_conn,
            purpose="answer",
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
            cost=cost,
        )
        result = await db_conn.execute(
            sa.text("SELECT cost_usd FROM onestop.llm_calls WHERE id = :id"),
            {"id": row_id},
        )
        assert Decimal(str(result.scalar_one())) == cost

    async def test_status_reflects_recorded_calls(self, db_conn: AsyncConnection):
        guard = PersistedSpendGuard(Decimal("5.00"), Decimal("50.00"))
        cost = Decimal("0.002")
        await guard.reserve(db_conn, cost)
        await guard.record(
            db_conn,
            purpose="answer",
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            input_tokens=200,
            output_tokens=100,
            cost=cost,
        )
        s = await guard.status(db_conn)
        assert s.day_usd >= cost
        assert s.month_usd >= cost

    async def test_day_cap_blocks_when_exceeded(self, db_conn: AsyncConnection):
        tiny_cap = Decimal("0.000001")
        guard = PersistedSpendGuard(tiny_cap, Decimal("50.00"))
        await guard.reserve(db_conn, tiny_cap)
        await guard.record(
            db_conn,
            purpose="answer",
            provider="ollama",
            model="llama3.2",
            input_tokens=1,
            output_tokens=1,
            cost=tiny_cap,
        )
        with pytest.raises(CapExceededError) as exc_info:
            await guard.reserve(db_conn, tiny_cap)
        assert exc_info.value.reason == "day_cap"

    async def test_kill_switch_blocks_all_calls(self, db_conn: AsyncConnection):
        guard = PersistedSpendGuard(Decimal("100.00"), Decimal("1000.00"))
        await guard.set_kill_switch(db_conn, True, actor_id=None)
        with pytest.raises(CapExceededError) as exc_info:
            await guard.reserve(db_conn, Decimal("0.001"))
        assert exc_info.value.reason == "kill_switch"

    async def test_set_kill_switch_upserts(self, db_conn: AsyncConnection):
        guard = PersistedSpendGuard(Decimal("100.00"), Decimal("1000.00"))
        await guard.set_kill_switch(db_conn, True)
        await guard.set_kill_switch(db_conn, False)
        s = await guard.status(db_conn)
        assert s.kill_switch is False

    async def test_reserve_allows_exact_cap(self, db_conn: AsyncConnection):
        guard = PersistedSpendGuard(Decimal("0.01"), Decimal("50.00"))
        await guard.reserve(db_conn, Decimal("0.01"))
