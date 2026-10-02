"""Integration tests for admin spend routes.

Requires a running Postgres test database (``docker compose up -d db``).
All tests are marked ``integration`` and excluded from the unit-test run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.platform.tables import t_login_codes, t_users

# ---------------------------------------------------------------------------
# Helpers (shared with other admin test files)
# ---------------------------------------------------------------------------


async def _login_as_admin(
    client: AsyncClient,
    conn: AsyncConnection,
    email: str = "admin_spend@test.com",
) -> tuple[str, str]:
    """Create admin user and session; return (session_token, csrf_token)."""
    from src.modules.platform.auth import _generate_otp, _hash_code  # noqa: PLC0415

    await conn.execute(sa.insert(t_users).values(email=email, role="admin", is_active=True))
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
    data = resp.json()
    token = str(resp.cookies.get("session") or "")
    csrf = str(data.get("csrf_token", ""))
    return token, csrf


@pytest.mark.integration
class TestGetSpend:
    async def test_requires_admin(self, client: AsyncClient, db_conn: AsyncConnection):
        """Non-admin users get 403."""
        from src.modules.platform.auth import _generate_otp, _hash_code  # noqa: PLC0415

        await db_conn.execute(
            sa.insert(t_users).values(email="staff_spend@test.com", role="staff", is_active=True)
        )
        raw_code = _generate_otp()
        await db_conn.execute(
            sa.insert(t_login_codes).values(
                email="staff_spend@test.com",
                code_hash=_hash_code(raw_code),
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
        resp = await client.post(
            "/api/v1/auth/verify-code",
            json={"email": "staff_spend@test.com", "code": raw_code},
        )
        token = str(resp.cookies.get("session") or "")

        resp2 = await client.get(
            "/api/v1/admin/spend",
            headers={"X-Session-Token": token},
        )
        assert resp2.status_code == 403

    async def test_returns_expected_keys(self, client: AsyncClient, db_conn: AsyncConnection):
        """Admin gets rows list and guard status object."""
        token, _ = await _login_as_admin(client, db_conn)
        resp = await client.get(
            "/api/v1/admin/spend?days=7",
            headers={"X-Session-Token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        assert "guard" in data
        guard = data["guard"]
        assert "day_spent_usd" in guard
        assert "month_spent_usd" in guard
        assert "day_cap_usd" in guard
        assert "month_cap_usd" in guard
        assert "kill_switch" in guard

    async def test_days_validation(self, client: AsyncClient, db_conn: AsyncConnection):
        """days=0 should return a 422."""
        token, _ = await _login_as_admin(client, db_conn, "admin_spend2@test.com")
        resp = await client.get(
            "/api/v1/admin/spend?days=0",
            headers={"X-Session-Token": token},
        )
        assert resp.status_code == 422


@pytest.mark.integration
class TestKillSwitch:
    async def test_toggle_kill_switch(self, client: AsyncClient, db_conn: AsyncConnection):
        """Admin can enable and disable the kill switch."""
        token, csrf = await _login_as_admin(client, db_conn, "admin_ks@test.com")

        # Enable
        resp_on = await client.post(
            "/api/v1/admin/spend/kill-switch",
            json={"enabled": True},
            headers={"X-Session-Token": token, "X-CSRF-Token": csrf},
        )
        assert resp_on.status_code == 200
        assert resp_on.json()["kill_switch"] is True

        # Disable
        resp_off = await client.post(
            "/api/v1/admin/spend/kill-switch",
            json={"enabled": False},
            headers={"X-Session-Token": token, "X-CSRF-Token": csrf},
        )
        assert resp_off.status_code == 200
        assert resp_off.json()["kill_switch"] is False

    async def test_requires_csrf(self, client: AsyncClient, db_conn: AsyncConnection):
        """Missing CSRF token returns 403."""
        token, _ = await _login_as_admin(client, db_conn, "admin_ks2@test.com")
        resp = await client.post(
            "/api/v1/admin/spend/kill-switch",
            json={"enabled": True},
            headers={"X-Session-Token": token},
        )
        assert resp.status_code == 403
