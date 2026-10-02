"""Tests for src.modules.platform.rate_limit."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.platform.rate_limit import check_and_increment

# ---------------------------------------------------------------------------
# Unit tests (no database — mock connection)
# ---------------------------------------------------------------------------


class TestCheckAndIncrement:
    def _make_conn(self, count: int) -> AsyncMock:
        conn = AsyncMock(spec=AsyncConnection)
        result = MagicMock()
        result.scalar_one.return_value = count
        conn.execute.return_value = result
        return conn

    async def test_returns_true_when_count_below_limit(self):
        conn = self._make_conn(count=3)
        assert await check_and_increment(conn, key="k", limit=5, window_seconds=60) is True

    async def test_returns_true_when_count_equals_limit(self):
        """The limit-th request is still allowed (limit is inclusive)."""
        conn = self._make_conn(count=5)
        assert await check_and_increment(conn, key="k", limit=5, window_seconds=60) is True

    async def test_returns_false_when_count_exceeds_limit(self):
        """The (limit + 1)-th request is blocked."""
        conn = self._make_conn(count=6)
        assert await check_and_increment(conn, key="k", limit=5, window_seconds=60) is False

    async def test_returns_false_well_above_limit(self):
        conn = self._make_conn(count=100)
        assert await check_and_increment(conn, key="k", limit=5, window_seconds=60) is False

    async def test_calls_execute_once(self):
        conn = self._make_conn(count=1)
        await check_and_increment(conn, key="login:user@x.com", limit=5, window_seconds=60)
        conn.execute.assert_awaited_once()

    async def test_limit_of_one_blocks_second_call(self):
        """A limit of 1 means only the very first request per window is allowed."""
        conn = self._make_conn(count=2)
        assert await check_and_increment(conn, key="k", limit=1, window_seconds=60) is False


# ---------------------------------------------------------------------------
# Integration tests (require docker compose up -d db)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCheckAndIncrementIntegration:
    async def test_first_call_is_allowed(self, db_conn: AsyncConnection):
        allowed = await check_and_increment(db_conn, key="int:rl:first", limit=5, window_seconds=60)
        assert allowed is True

    async def test_limit_is_enforced(self, db_conn: AsyncConnection):
        key = "int:rl:enforce"
        for n in range(1, 4):
            result = await check_and_increment(db_conn, key=key, limit=3, window_seconds=60)
            assert result is True, f"call {n} should be allowed"
        # 4th call exceeds limit of 3
        assert await check_and_increment(db_conn, key=key, limit=3, window_seconds=60) is False

    async def test_limit_one_blocks_second_call(self, db_conn: AsyncConnection):
        key = "int:rl:limit1"
        assert await check_and_increment(db_conn, key=key, limit=1, window_seconds=60) is True
        assert await check_and_increment(db_conn, key=key, limit=1, window_seconds=60) is False

    async def test_different_keys_are_independent(self, db_conn: AsyncConnection):
        """Exhausting one key must not affect another key's counter."""
        key_a = "int:rl:keya"
        key_b = "int:rl:keyb"
        for _ in range(3):
            await check_and_increment(db_conn, key=key_a, limit=3, window_seconds=60)
        # key_a is now at limit; key_b is untouched
        assert await check_and_increment(db_conn, key=key_b, limit=3, window_seconds=60) is True

    async def test_counter_persists_above_limit(self, db_conn: AsyncConnection):
        """Counter keeps incrementing after the limit so we can audit abuse."""
        key = "int:rl:persist"
        for _ in range(5):
            await check_and_increment(db_conn, key=key, limit=2, window_seconds=60)
        result = await db_conn.execute(
            sa.text("SELECT count FROM onestop.rate_limits WHERE key = :k"),
            {"k": key},
        )
        assert result.scalar() == 5

    async def test_row_upserted_in_rate_limits_table(self, db_conn: AsyncConnection):
        key = "int:rl:row"
        await check_and_increment(db_conn, key=key, limit=10, window_seconds=60)
        result = await db_conn.execute(
            sa.text("SELECT count FROM onestop.rate_limits WHERE key = :k"),
            {"k": key},
        )
        assert result.scalar() == 1
