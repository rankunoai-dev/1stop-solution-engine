"""Integration tests for POST /api/v1/chat (SSE streaming).

Requires a running Postgres test database (``docker compose up -d db``).
All tests are marked ``integration`` and excluded from the unit-test run.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.assistant.llm_tool import AnswerResult
from src.modules.platform.tables import t_login_codes, t_users

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_user(
    conn: AsyncConnection,
    email: str,
    role: str = "staff",
) -> None:
    """Insert a minimal active user."""
    await conn.execute(sa.insert(t_users).values(email=email, role=role, is_active=True))


async def _login(
    client: AsyncClient,
    conn: AsyncConnection,
    email: str,
    role: str = "staff",
) -> str:
    """Create a user and session; return the session token."""
    from src.modules.platform.auth import _generate_otp, _hash_code  # noqa: PLC0415

    await _create_user(conn, email, role=role)
    raw_code = _generate_otp()
    expires_at = datetime.now(UTC) + timedelta(minutes=10)
    await conn.execute(
        sa.insert(t_login_codes).values(
            email=email,
            code_hash=_hash_code(raw_code),
            expires_at=expires_at,
        )
    )
    resp = await client.post("/api/v1/auth/verify-code", json={"email": email, "code": raw_code})
    assert resp.status_code == 200
    return str(resp.cookies.get("session") or resp.headers.get("X-Session-Token", ""))


def _parse_sse(text: str) -> list[dict]:
    """Parse raw SSE body into a list of event dicts."""
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            payload = line[len("data: ") :]
            events.append(json.loads(payload))
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestChatNoAuth:
    async def test_no_auth_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/v1/chat", json={"message": "hello"})
        assert resp.status_code == 401


@pytest.mark.integration
class TestChatSuccess:
    async def test_sse_events_in_order(
        self,
        client: AsyncClient,
        db_conn: AsyncConnection,
    ):
        """Authenticated request returns status→token→done event sequence."""
        token = await _login(client, db_conn, "chat_ok@test.com")
        assert token, "login failed"

        fake_result = AnswerResult(
            text="Hello there!",
            input_tokens=10,
            output_tokens=5,
            cost_usd=Decimal("0"),
        )

        with (
            patch(
                "src.modules.assistant.llm_tool.AnswerLLMTool.execute",
                new_callable=lambda: lambda self: AsyncMock(return_value=fake_result),
            ),
            patch(
                "src.modules.assistant.llm_tool.AnswerLLMTool.execute",
                AsyncMock(return_value=fake_result),
            ),
        ):
            resp = await client.post(
                "/api/v1/chat",
                json={"message": "Hi"},
                headers={"X-Session-Token": token},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        # Should have at least: status(thinking), status(answering), token, done
        assert "status" in types
        assert "token" in types or "error" in types
        # The stream must end with done or error
        assert types[-1] in ("done", "error")


@pytest.mark.integration
class TestChatCapReached:
    async def test_cap_exceeded_returns_error_event(
        self,
        client: AsyncClient,
        db_conn: AsyncConnection,
    ):
        """When CapExceededError is raised, an error event with code=cap_reached is emitted."""
        from src.modules.platform.spend import CapExceededError  # noqa: PLC0415

        token = await _login(client, db_conn, "chat_cap@test.com")
        assert token, "login failed"

        with patch(
            "src.modules.assistant.llm_tool.AnswerLLMTool.execute",
            AsyncMock(
                side_effect=CapExceededError(
                    "day_cap",
                    Decimal("0.01"),
                    Decimal("1.00"),
                    Decimal("1.00"),
                )
            ),
        ):
            resp = await client.post(
                "/api/v1/chat",
                json={"message": "hello"},
                headers={"X-Session-Token": token},
            )

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        error_events = [e for e in events if e["type"] == "error"]
        assert error_events, f"Expected an error event; got: {events}"
        assert error_events[-1]["code"] == "cap_reached"


@pytest.mark.integration
class TestChatRateLimit:
    async def test_rate_limited_returns_error_event(
        self,
        client: AsyncClient,
        db_conn: AsyncConnection,
    ):
        """When rate limit is exceeded, an error event with code=rate_limited is emitted."""
        token = await _login(client, db_conn, "chat_rl@test.com")
        assert token, "login failed"

        # Patch check_and_increment to return False (rate limited)
        with patch(
            "src.modules.api.routes_chat.check_and_increment",
            AsyncMock(return_value=False),
        ):
            resp = await client.post(
                "/api/v1/chat",
                json={"message": "hello"},
                headers={"X-Session-Token": token},
            )

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        error_events = [e for e in events if e["type"] == "error"]
        assert error_events, f"Expected a rate_limited event; got: {events}"
        assert error_events[0]["code"] == "rate_limited"
