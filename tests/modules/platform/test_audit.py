"""Tests for src.modules.platform.audit."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.platform.audit import record

# ---------------------------------------------------------------------------
# Unit tests (no database)
# ---------------------------------------------------------------------------


class TestRecord:
    async def test_calls_execute_once(self):
        conn = AsyncMock(spec=AsyncConnection)
        await record(conn, action="test.action", target="test:target")
        assert conn.execute.await_count == 1

    async def test_insert_statement_passed(self):
        conn = AsyncMock(spec=AsyncConnection)
        await record(conn, action="test.action", target="test:target")
        stmt = conn.execute.call_args[0][0]
        assert isinstance(stmt, sa.Insert)

    async def test_detail_defaults_to_empty_dict(self):
        """None detail is converted to {} before hitting the DB."""
        conn = AsyncMock(spec=AsyncConnection)
        await record(conn, action="test.action", target="test:target", detail=None)
        conn.execute.assert_awaited_once()

    async def test_explicit_detail_passed_through(self):
        conn = AsyncMock(spec=AsyncConnection)
        await record(
            conn,
            action="test.action",
            target="test:target",
            detail={"ip": "1.2.3.4"},
        )
        conn.execute.assert_awaited_once()

    async def test_actor_user_id_optional(self):
        conn = AsyncMock(spec=AsyncConnection)
        await record(conn, action="test.action", target="test:target")
        conn.execute.assert_awaited_once()

    async def test_with_actor_user_id(self):
        conn = AsyncMock(spec=AsyncConnection)
        actor_id = uuid.uuid4()
        await record(
            conn,
            action="login.code_verified",
            target=f"user:{actor_id}",
            actor_user_id=actor_id,
        )
        conn.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# Integration tests (require docker compose up -d db)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRecordIntegration:
    async def test_row_is_inserted(self, db_conn: AsyncConnection):
        await record(db_conn, action="int.inserted", target="test:row")
        result = await db_conn.execute(
            sa.text("SELECT action, target FROM onestop.audit_log WHERE action = 'int.inserted'")
        )
        row = result.fetchone()
        assert row is not None
        assert row.action == "int.inserted"
        assert row.target == "test:row"

    async def test_id_is_auto_generated(self, db_conn: AsyncConnection):
        await record(db_conn, action="int.autoid", target="test:id")
        result = await db_conn.execute(
            sa.text("SELECT id FROM onestop.audit_log WHERE action = 'int.autoid'")
        )
        row_id = result.scalar()
        assert isinstance(row_id, int)
        assert row_id > 0

    async def test_detail_stored_as_jsonb(self, db_conn: AsyncConnection):
        await record(
            db_conn,
            action="int.detail",
            target="test:detail",
            detail={"ip": "10.0.0.1", "attempts": 3},
        )
        result = await db_conn.execute(
            sa.text("SELECT detail FROM onestop.audit_log WHERE action = 'int.detail'")
        )
        detail = result.scalar()
        assert detail == {"ip": "10.0.0.1", "attempts": 3}

    async def test_detail_defaults_to_empty_jsonb(self, db_conn: AsyncConnection):
        await record(db_conn, action="int.nodetail", target="test:nd")
        result = await db_conn.execute(
            sa.text("SELECT detail FROM onestop.audit_log WHERE action = 'int.nodetail'")
        )
        assert result.scalar() == {}

    async def test_actor_user_id_is_nullable(self, db_conn: AsyncConnection):
        await record(
            db_conn,
            action="int.system",
            target="test:sys",
            actor_user_id=None,
        )
        result = await db_conn.execute(
            sa.text("SELECT actor_user_id FROM onestop.audit_log WHERE action = 'int.system'")
        )
        assert result.scalar() is None

    async def test_rows_ordered_by_identity(self, db_conn: AsyncConnection):
        """IDENTITY pk guarantees strict insertion order even across concurrent writes."""
        for i in range(3):
            await record(db_conn, action=f"int.seq.{i}", target="test:order")
        result = await db_conn.execute(
            sa.text("SELECT action FROM onestop.audit_log WHERE target = 'test:order' ORDER BY id")
        )
        actions = [r[0] for r in result.fetchall()]
        assert actions == ["int.seq.0", "int.seq.1", "int.seq.2"]
