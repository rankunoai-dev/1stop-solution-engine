"""Integration tests for authentication routes.

Requires a running Postgres test database (``docker compose up -d db``).
All tests are marked ``integration`` and excluded from the unit-test run.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.platform.tables import t_login_codes, t_users


async def _create_active_user(conn: AsyncConnection, email: str, role: str = "staff") -> None:
    """Insert a minimal active user directly into the test DB."""
    await conn.execute(sa.insert(t_users).values(email=email, role=role, is_active=True))


async def _get_login_code(conn: AsyncConnection, email: str) -> str | None:
    """Fetch the most recent unconsumed login code for *email*."""
    result = await conn.execute(
        sa.select(t_login_codes.c.code_hash)
        .where(
            t_login_codes.c.email == email,
            t_login_codes.c.consumed_at.is_(None),
        )
        .order_by(t_login_codes.c.created_at.desc())
        .limit(1)
    )
    row = result.fetchone()
    return str(row[0]) if row else None


@pytest.mark.integration
class TestRequestCode:
    async def test_unknown_email_returns_200_generic(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/request-code", json={"email": "nobody@nowhere.com"})
        assert resp.status_code == 200
        assert "registered" in resp.json()["detail"]

    async def test_known_active_user_returns_200(
        self, client: AsyncClient, db_conn: AsyncConnection
    ):
        await _create_active_user(db_conn, "rq_user@test.com")
        resp = await client.post("/api/v1/auth/request-code", json={"email": "rq_user@test.com"})
        assert resp.status_code == 200


@pytest.mark.integration
class TestVerifyCode:
    async def test_invalid_code_returns_422(self, client: AsyncClient, db_conn: AsyncConnection):
        await _create_active_user(db_conn, "vc_user1@test.com")
        # Request code so a code row exists.
        await client.post("/api/v1/auth/request-code", json={"email": "vc_user1@test.com"})
        resp = await client.post(
            "/api/v1/auth/verify-code",
            json={"email": "vc_user1@test.com", "code": "000000"},
        )
        assert resp.status_code == 422

    async def test_full_login_flow(self, client: AsyncClient, db_conn: AsyncConnection):
        email = "login_flow@test.com"
        await _create_active_user(db_conn, email)

        # Step 1: request a login code (inserts row in login_codes via test conn).
        from datetime import UTC, datetime, timedelta

        from src.modules.platform.auth import _generate_otp
        from src.modules.platform.auth import _hash_code as hc
        from src.modules.platform.tables import t_login_codes

        raw_code = _generate_otp()
        code_hash = hc(raw_code)
        expires_at = datetime.now(UTC) + timedelta(minutes=10)
        await db_conn.execute(
            sa.insert(t_login_codes).values(email=email, code_hash=code_hash, expires_at=expires_at)
        )

        # Step 2: verify the code.
        resp = await client.post(
            "/api/v1/auth/verify-code",
            json={"email": email, "code": raw_code},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "csrf_token" in data
        assert data["user"]["email"] == email
        # Session cookie must be set.
        assert "session" in resp.cookies


@pytest.mark.integration
class TestLogout:
    async def test_logout_revokes_session(self, client: AsyncClient, db_conn: AsyncConnection):
        email = "logout_user@test.com"
        await _create_active_user(db_conn, email)

        from datetime import UTC, datetime, timedelta

        from src.modules.platform.auth import _generate_otp
        from src.modules.platform.auth import _hash_code as hc

        raw_code = _generate_otp()
        expires_at = datetime.now(UTC) + timedelta(minutes=10)
        await db_conn.execute(
            sa.insert(t_login_codes).values(
                email=email, code_hash=hc(raw_code), expires_at=expires_at
            )
        )
        # Login to get session + CSRF.
        login_resp = await client.post(
            "/api/v1/auth/verify-code", json={"email": email, "code": raw_code}
        )
        assert login_resp.status_code == 200
        csrf = login_resp.json()["csrf_token"]

        # Logout.
        resp = await client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf},
            cookies=login_resp.cookies,
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Logged out."

    async def test_csrf_required_for_logout(self, client: AsyncClient, db_conn: AsyncConnection):
        email = "csrf_logout@test.com"
        await _create_active_user(db_conn, email)

        from datetime import UTC, datetime, timedelta

        from src.modules.platform.auth import _generate_otp
        from src.modules.platform.auth import _hash_code as hc

        raw_code = _generate_otp()
        expires_at = datetime.now(UTC) + timedelta(minutes=10)
        await db_conn.execute(
            sa.insert(t_login_codes).values(
                email=email, code_hash=hc(raw_code), expires_at=expires_at
            )
        )
        login_resp = await client.post(
            "/api/v1/auth/verify-code", json={"email": email, "code": raw_code}
        )
        assert login_resp.status_code == 200

        # Logout WITHOUT CSRF header → 403.
        resp = await client.post(
            "/api/v1/auth/logout",
            cookies=login_resp.cookies,
        )
        assert resp.status_code == 403


@pytest.mark.integration
class TestMe:
    async def test_me_returns_user_after_login(self, client: AsyncClient, db_conn: AsyncConnection):
        email = "me_user@test.com"
        await _create_active_user(db_conn, email)

        from datetime import UTC, datetime, timedelta

        from src.modules.platform.auth import _generate_otp
        from src.modules.platform.auth import _hash_code as hc

        raw_code = _generate_otp()
        expires_at = datetime.now(UTC) + timedelta(minutes=10)
        await db_conn.execute(
            sa.insert(t_login_codes).values(
                email=email, code_hash=hc(raw_code), expires_at=expires_at
            )
        )
        login_resp = await client.post(
            "/api/v1/auth/verify-code", json={"email": email, "code": raw_code}
        )
        assert login_resp.status_code == 200

        me_resp = await client.get("/api/v1/me", cookies=login_resp.cookies)
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == email

    async def test_me_returns_401_without_session(self, client: AsyncClient):
        resp = await client.get("/api/v1/me")
        assert resp.status_code == 401
