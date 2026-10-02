"""Integration tests for admin job-queue routes.

Requires a running Postgres test database (``docker compose up -d db``).
All tests are marked ``integration`` and excluded from the unit-test run.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.platform.tables import t_jobs, t_login_codes, t_users

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _login_as_admin(
    client: AsyncClient,
    conn: AsyncConnection,
    email: str = "admin_jobs@test.com",
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


async def _insert_job(
    conn: AsyncConnection,
    status: str = "queued",
    kind: str = "test.job",
) -> uuid.UUID:
    """Insert a minimal job row and return its id."""
    job_id = uuid.uuid4()
    await conn.execute(
        sa.insert(t_jobs).values(
            id=job_id,
            kind=kind,
            status=status,
            run_after=datetime.now(UTC),
        )
    )
    return job_id


@pytest.mark.integration
class TestListJobs:
    async def test_returns_list(self, client: AsyncClient, db_conn: AsyncConnection):
        token, _ = await _login_as_admin(client, db_conn)
        await _insert_job(db_conn, status="queued")

        resp = await client.get(
            "/api/v1/admin/jobs",
            headers={"X-Session-Token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_row_has_expected_keys(self, client: AsyncClient, db_conn: AsyncConnection):
        token, _ = await _login_as_admin(client, db_conn, "admin_jobs_keys@test.com")
        await _insert_job(db_conn)

        resp = await client.get(
            "/api/v1/admin/jobs",
            headers={"X-Session-Token": token},
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert rows  # at least one row
        row = rows[0]
        for key in ("id", "kind", "status", "attempts", "has_payload", "error"):
            assert key in row, f"Missing key: {key}"

    async def test_no_payload_returned(self, client: AsyncClient, db_conn: AsyncConnection):
        """Raw payload must never be exposed by this endpoint."""
        token, _ = await _login_as_admin(client, db_conn, "admin_jobs_nopay@test.com")
        await _insert_job(db_conn)

        resp = await client.get(
            "/api/v1/admin/jobs",
            headers={"X-Session-Token": token},
        )
        rows = resp.json()
        for row in rows:
            assert "payload" not in row

    async def test_status_filter(self, client: AsyncClient, db_conn: AsyncConnection):
        token, _ = await _login_as_admin(client, db_conn, "admin_jobs_filter@test.com")
        await _insert_job(db_conn, status="dead")

        resp = await client.get(
            "/api/v1/admin/jobs?status=dead",
            headers={"X-Session-Token": token},
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert all(r["status"] == "dead" for r in rows)

    async def test_requires_admin(self, client: AsyncClient, db_conn: AsyncConnection):
        from src.modules.platform.auth import _generate_otp, _hash_code  # noqa: PLC0415

        await db_conn.execute(
            sa.insert(t_users).values(email="staff_jobs@test.com", role="staff", is_active=True)
        )
        raw_code = _generate_otp()
        await db_conn.execute(
            sa.insert(t_login_codes).values(
                email="staff_jobs@test.com",
                code_hash=_hash_code(raw_code),
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
        resp = await client.post(
            "/api/v1/auth/verify-code",
            json={"email": "staff_jobs@test.com", "code": raw_code},
        )
        token = str(resp.cookies.get("session") or "")

        resp2 = await client.get(
            "/api/v1/admin/jobs",
            headers={"X-Session-Token": token},
        )
        assert resp2.status_code == 403


@pytest.mark.integration
class TestRetryJob:
    async def test_retry_dead_job(self, client: AsyncClient, db_conn: AsyncConnection):
        """A dead job is reset to queued."""
        token, csrf = await _login_as_admin(client, db_conn, "admin_retry@test.com")
        job_id = await _insert_job(db_conn, status="dead")

        resp = await client.post(
            f"/api/v1/admin/jobs/{job_id}/retry",
            headers={"X-Session-Token": token, "X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["attempts"] == 0

    async def test_retry_failed_job(self, client: AsyncClient, db_conn: AsyncConnection):
        """A failed job is also reset to queued."""
        token, csrf = await _login_as_admin(client, db_conn, "admin_retry2@test.com")
        job_id = await _insert_job(db_conn, status="failed")

        resp = await client.post(
            f"/api/v1/admin/jobs/{job_id}/retry",
            headers={"X-Session-Token": token, "X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    async def test_retry_nonexistent_job_returns_404(
        self, client: AsyncClient, db_conn: AsyncConnection
    ):
        token, csrf = await _login_as_admin(client, db_conn, "admin_retry3@test.com")
        resp = await client.post(
            f"/api/v1/admin/jobs/{uuid.uuid4()}/retry",
            headers={"X-Session-Token": token, "X-CSRF-Token": csrf},
        )
        assert resp.status_code == 404

    async def test_retry_queued_job_returns_422(
        self, client: AsyncClient, db_conn: AsyncConnection
    ):
        """Cannot retry a job that is already queued."""
        token, csrf = await _login_as_admin(client, db_conn, "admin_retry4@test.com")
        job_id = await _insert_job(db_conn, status="queued")

        resp = await client.post(
            f"/api/v1/admin/jobs/{job_id}/retry",
            headers={"X-Session-Token": token, "X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422
