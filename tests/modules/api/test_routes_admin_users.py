"""Integration tests for admin user-management routes.

Requires a running Postgres test database (``docker compose up -d db``).
All tests are marked ``integration`` and excluded from the unit-test run.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.platform.auth import (
    _generate_otp,
    _hash_code,
)
from src.modules.platform.tables import t_users

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_user(
    conn: AsyncConnection,
    email: str,
    role: str = "staff",
    is_active: bool = True,
) -> uuid.UUID:
    """Insert a user and return its id."""
    user_id = uuid.uuid4()
    await conn.execute(
        sa.insert(t_users).values(id=user_id, email=email, role=role, is_active=is_active)
    )
    return user_id


async def _login(
    client: AsyncClient,
    conn: AsyncConnection,
    email: str,
    role: str = "staff",
) -> tuple[str, dict]:
    """Create a user + session; return (csrf_token, cookies)."""
    from datetime import UTC, datetime, timedelta

    from src.modules.platform.tables import t_login_codes

    await _create_user(conn, email, role=role)
    raw_code = _generate_otp()
    expires_at = datetime.now(UTC) + timedelta(minutes=10)
    await conn.execute(
        sa.insert(t_login_codes).values(
            email=email, code_hash=_hash_code(raw_code), expires_at=expires_at
        )
    )
    resp = await client.post("/api/v1/auth/verify-code", json={"email": email, "code": raw_code})
    assert resp.status_code == 200
    data = resp.json()
    return data["csrf_token"], dict(resp.cookies)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListUsers:
    async def test_requires_admin(self, client: AsyncClient, db_conn: AsyncConnection):
        csrf, cookies = await _login(client, db_conn, "staff_list@test.com", role="staff")
        resp = await client.get(
            "/api/v1/admin/users",
            headers={"X-CSRF-Token": csrf},
            cookies=cookies,
        )
        assert resp.status_code == 403

    async def test_admin_gets_list_with_stats(self, client: AsyncClient, db_conn: AsyncConnection):
        csrf, cookies = await _login(client, db_conn, "admin_list@test.com", role="admin")
        resp = await client.get(
            "/api/v1/admin/users",
            headers={"X-CSRF-Token": csrf},
            cookies=cookies,
        )
        assert resp.status_code == 200
        users = resp.json()
        assert isinstance(users, list)
        assert len(users) >= 1
        first = users[0]
        for field in (
            "id",
            "email",
            "role",
            "is_active",
            "active_sessions",
            "llm_call_count",
            "total_cost_usd",
        ):
            assert field in first, f"Missing field: {field}"


@pytest.mark.integration
class TestCreateUser:
    async def test_admin_creates_user(self, client: AsyncClient, db_conn: AsyncConnection):
        csrf, cookies = await _login(client, db_conn, "admin_create@test.com", role="admin")
        resp = await client.post(
            "/api/v1/admin/users",
            json={"email": "new_staff@test.com", "role": "staff"},
            headers={"X-CSRF-Token": csrf},
            cookies=cookies,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "new_staff@test.com"
        assert data["role"] == "staff"

    async def test_duplicate_email_returns_409(self, client: AsyncClient, db_conn: AsyncConnection):
        csrf, cookies = await _login(client, db_conn, "admin_dup@test.com", role="admin")
        await _create_user(db_conn, "dup_target@test.com")
        resp = await client.post(
            "/api/v1/admin/users",
            json={"email": "dup_target@test.com", "role": "staff"},
            headers={"X-CSRF-Token": csrf},
            cookies=cookies,
        )
        assert resp.status_code == 409


@pytest.mark.integration
class TestPatchUser:
    async def test_admin_changes_role(self, client: AsyncClient, db_conn: AsyncConnection):
        csrf, cookies = await _login(client, db_conn, "admin_patch@test.com", role="admin")
        target_id = await _create_user(db_conn, "patch_target@test.com", role="staff")
        resp = await client.patch(
            f"/api/v1/admin/users/{target_id}",
            json={"role": "admin"},
            headers={"X-CSRF-Token": csrf},
            cookies=cookies,
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    async def test_last_admin_cannot_be_deactivated(
        self, client: AsyncClient, db_conn: AsyncConnection
    ):
        """The only active admin cannot deactivate themselves."""
        csrf, cookies = await _login(client, db_conn, "sole_admin@test.com", role="admin")
        # Get the admin's own user_id from /me.
        me_resp = await client.get("/api/v1/me", cookies=cookies)
        admin_id = me_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/admin/users/{admin_id}",
            json={"is_active": False},
            headers={"X-CSRF-Token": csrf},
            cookies=cookies,
        )
        # Either 422 (last admin guard) or 422 (self-deactivation guard).
        assert resp.status_code == 422

    async def test_cannot_deactivate_self(self, client: AsyncClient, db_conn: AsyncConnection):
        csrf, cookies = await _login(client, db_conn, "self_deact@test.com", role="admin")
        # Add a second admin so the last-admin guard doesn't fire first.
        await _create_user(db_conn, "second_admin@test.com", role="admin")

        me_resp = await client.get("/api/v1/me", cookies=cookies)
        my_id = me_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/admin/users/{my_id}",
            json={"is_active": False},
            headers={"X-CSRF-Token": csrf},
            cookies=cookies,
        )
        assert resp.status_code == 422
        assert "self" in resp.json()["detail"].lower() or "own" in resp.json()["detail"].lower()
