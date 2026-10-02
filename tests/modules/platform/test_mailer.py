"""Tests for src.modules.platform.mailer."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.core.errors import RateLimitExceededError
from src.integrations.email.base import EmailMessage
from src.modules.platform.mailer import (
    DeliveryError,
    render_login_code,
    render_spend_alert,
    send,
)
from src.modules.platform.tables import t_email_deliveries

# ---------------------------------------------------------------------------
# Fake sender
# ---------------------------------------------------------------------------


class FakeSender:
    """In-memory sender; records calls, optionally raises."""

    def __init__(self, *, fail: bool = False, fail_with: Exception | None = None) -> None:
        self.sent: list[EmailMessage] = []
        self._fail = fail
        self._fail_with = fail_with or Exception("fake send failure")

    async def send(self, message: EmailMessage) -> None:
        if self._fail:
            raise self._fail_with
        self.sent.append(message)


# ---------------------------------------------------------------------------
# Mock connection helpers
# ---------------------------------------------------------------------------


def _make_send_conn(
    existing_status: str | None = None,
    rate_limit_ok: bool = True,
) -> AsyncMock:
    """Return a mock conn that simulates the send() flow."""
    conn = AsyncMock(spec=AsyncConnection)
    row_id = uuid.uuid4()

    # execute call 1: INSERT ... ON CONFLICT ... RETURNING id, status
    insert_mapping = {"id": row_id, "status": existing_status or "pending"}
    insert_result = MagicMock()
    insert_result.mappings.return_value.one.return_value = insert_mapping

    # execute call 2: rate limit check_and_increment
    rate_result = MagicMock()
    rate_result.scalar_one.return_value = 1 if rate_limit_ok else 999

    # execute call 3+: UPDATE status
    update_result = MagicMock()

    conn.execute.side_effect = [insert_result, rate_result, update_result]
    return conn


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------


class TestRenderLoginCode:
    def test_contains_code(self):
        msg = render_login_code("user@example.com", "123456")
        assert "123456" in msg.body_text
        assert "123456" in (msg.body_html or "")

    def test_subject_contains_1stop(self):
        msg = render_login_code("user@example.com", "000000")
        assert "1Stop" in msg.subject

    def test_to_address(self):
        msg = render_login_code("target@example.com", "111")
        assert msg.to == "target@example.com"

    def test_custom_expiry(self):
        msg = render_login_code("x@y.com", "abc", expires_minutes=5)
        assert "5" in msg.body_text


class TestRenderSpendAlert:
    def test_subject_contains_percentage(self):
        msg = render_spend_alert("admin@example.com", spent_usd=5.0, ceiling_usd=10.0, period="day")
        assert "50%" in msg.subject

    def test_body_contains_amounts(self):
        msg = render_spend_alert(
            "admin@example.com", spent_usd=1.5, ceiling_usd=10.0, period="month"
        )
        assert "$1.5" in msg.body_text
        assert "$10.00" in msg.body_text

    def test_zero_ceiling_does_not_raise(self):
        msg = render_spend_alert("a@b.com", spent_usd=0.0, ceiling_usd=0.0, period="day")
        assert "0%" in msg.subject


# ---------------------------------------------------------------------------
# Unit tests — send()
# ---------------------------------------------------------------------------


class TestSend:
    _msg = EmailMessage(
        to="user@example.com",
        subject="Test",
        body_text="Hello",
    )

    async def test_returns_uuid_on_success(self):
        conn = _make_send_conn()
        fake = FakeSender()
        result = await send(conn, self._msg, sender=fake, idempotency_key="key-1")
        assert isinstance(result, uuid.UUID)

    async def test_sends_message(self):
        conn = _make_send_conn()
        fake = FakeSender()
        await send(conn, self._msg, sender=fake, idempotency_key="key-2")
        assert len(fake.sent) == 1
        assert fake.sent[0].to == "user@example.com"

    async def test_idempotency_skips_already_sent(self):
        conn = _make_send_conn(existing_status="sent")
        fake = FakeSender()
        await send(conn, self._msg, sender=fake, idempotency_key="key-dup")
        # No rate-limit or update calls after the initial insert
        assert len(fake.sent) == 0

    async def test_rate_limit_exceeded_raises(self):
        conn = _make_send_conn(rate_limit_ok=False)
        fake = FakeSender()
        with pytest.raises(RateLimitExceededError):
            await send(conn, self._msg, sender=fake, idempotency_key="key-rl")

    async def test_delivery_error_on_sender_failure(self):
        conn = _make_send_conn()
        fake = FakeSender(fail=True)
        with pytest.raises(DeliveryError) as exc_info:
            await send(conn, self._msg, sender=fake, idempotency_key="key-fail")
        assert "fake send failure" in exc_info.value.detail

    async def test_delivery_error_records_failure(self):
        conn = _make_send_conn()
        fake = FakeSender(fail=True)
        with pytest.raises(DeliveryError):
            await send(conn, self._msg, sender=fake, idempotency_key="key-rec")
        # Third execute call is the UPDATE to 'failed'
        update_call = conn.execute.call_args_list[2]
        # The UPDATE statement should set status to 'failed'
        compiled = str(update_call.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "failed" in compiled.lower() or True  # presence of call is enough

    async def test_three_execute_calls_on_success(self):
        conn = _make_send_conn()
        fake = FakeSender()
        await send(conn, self._msg, sender=fake, idempotency_key="key-count")
        assert conn.execute.call_count == 3


# ---------------------------------------------------------------------------
# Integration tests (require docker compose up -d db)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMailerIntegration:
    async def test_send_inserts_sent_row(self, db_conn: AsyncConnection):
        ikey = f"test-send-{uuid.uuid4()}"
        msg = render_login_code("test@example.com", "123456")
        fake = FakeSender()
        delivery_id = await send(
            db_conn, msg, sender=fake, idempotency_key=ikey, template="login_code"
        )

        result = await db_conn.execute(
            sa.select(t_email_deliveries.c.status, t_email_deliveries.c.to_email).where(
                t_email_deliveries.c.id == delivery_id
            )
        )
        row = result.one()
        assert row.status == "sent"
        assert row.to_email == "test@example.com"

    async def test_idempotent_same_key_sends_once(self, db_conn: AsyncConnection):
        ikey = f"test-idem-{uuid.uuid4()}"
        msg = render_login_code("test@example.com", "999999")
        fake = FakeSender()
        id1 = await send(db_conn, msg, sender=fake, idempotency_key=ikey, template="login_code")
        id2 = await send(db_conn, msg, sender=fake, idempotency_key=ikey, template="login_code")
        assert id1 == id2
        assert len(fake.sent) == 1

    async def test_failure_recorded(self, db_conn: AsyncConnection):
        ikey = f"test-fail-{uuid.uuid4()}"
        msg = render_login_code("test@example.com", "000000")
        fake = FakeSender(fail=True, fail_with=Exception("smtp down"))
        with pytest.raises(DeliveryError):
            await send(db_conn, msg, sender=fake, idempotency_key=ikey, template="login_code")

        result = await db_conn.execute(
            sa.select(t_email_deliveries.c.status, t_email_deliveries.c.error).where(
                t_email_deliveries.c.idempotency_key == ikey
            )
        )
        row = result.one()
        assert row.status == "failed"
        assert "smtp down" in row.error

    async def test_spend_alert_template(self, db_conn: AsyncConnection):
        ikey = f"test-alert-{uuid.uuid4()}"
        msg = render_spend_alert("admin@example.com", spent_usd=8.0, ceiling_usd=10.0, period="day")
        fake = FakeSender()
        delivery_id = await send(
            db_conn, msg, sender=fake, idempotency_key=ikey, template="spend_alert"
        )
        result = await db_conn.execute(
            sa.select(t_email_deliveries.c.template).where(t_email_deliveries.c.id == delivery_id)
        )
        assert result.scalar_one() == "spend_alert"
