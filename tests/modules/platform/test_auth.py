"""Unit tests for src.modules.platform.auth."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.platform.auth import (
    UserRow,
    VerifyResult,
    _generate_otp,
    _hash_code,
    bootstrap_admin,
    check_csrf_token,
    create_session,
    generate_csrf_token,
    lookup_session,
    request_login_code,
    revoke_session,
    verify_login_code,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conn() -> AsyncMock:
    """Return an AsyncMock with spec=AsyncConnection."""
    conn = AsyncMock(spec=AsyncConnection)
    result = MagicMock()
    result.scalar_one.return_value = None
    result.rowcount = 1
    conn.execute.return_value = result
    return conn


def _make_select_conn(mapping: dict | None) -> AsyncMock:
    """Return a conn whose execute() returns a single-row mapping or None."""
    conn = AsyncMock(spec=AsyncConnection)
    result = MagicMock()
    result.mappings.return_value.fetchone.return_value = mapping
    result.rowcount = 1 if mapping else 0
    conn.execute.return_value = result
    return conn


# ---------------------------------------------------------------------------
# _generate_otp
# ---------------------------------------------------------------------------


class TestGenerateOtp:
    def test_produces_six_digit_string(self):
        otp = _generate_otp()
        assert len(otp) == 6
        assert otp.isdigit()

    def test_zero_padded(self):
        # Run many times to get statistical coverage; all must be 6 chars.
        for _ in range(50):
            otp = _generate_otp()
            assert len(otp) == 6


# ---------------------------------------------------------------------------
# _hash_code
# ---------------------------------------------------------------------------


class TestHashCode:
    def test_deterministic(self):
        assert _hash_code("123456") == _hash_code("123456")

    def test_not_plaintext(self):
        h = _hash_code("123456")
        assert h != "123456"

    def test_hex_string(self):
        h = _hash_code("123456")
        int(h, 16)  # should not raise

    def test_different_codes_differ(self):
        assert _hash_code("000001") != _hash_code("000002")


# ---------------------------------------------------------------------------
# generate_csrf_token / check_csrf_token
# ---------------------------------------------------------------------------


class TestCsrfTokens:
    _TOKEN = "some_raw_session_token_value"
    _SECRET = "supersecretkey1234567890abcdef"

    def test_round_trip(self):
        csrf = generate_csrf_token(self._TOKEN, self._SECRET)
        assert check_csrf_token(csrf, self._TOKEN, self._SECRET)

    def test_wrong_token_rejected(self):
        csrf = generate_csrf_token(self._TOKEN, self._SECRET)
        assert not check_csrf_token("wrong" + csrf, self._TOKEN, self._SECRET)

    def test_wrong_session_rejected(self):
        csrf = generate_csrf_token(self._TOKEN, self._SECRET)
        assert not check_csrf_token(csrf, "other_session", self._SECRET)

    def test_wrong_secret_rejected(self):
        csrf = generate_csrf_token(self._TOKEN, self._SECRET)
        assert not check_csrf_token(csrf, self._TOKEN, "different_secret")

    def test_returns_bool_false(self):
        result = check_csrf_token("bad", self._TOKEN, self._SECRET)
        assert result is False


# ---------------------------------------------------------------------------
# request_login_code
# ---------------------------------------------------------------------------


class TestRequestLoginCode:
    async def test_no_op_when_user_not_found(self):
        """When the user does not exist, no insert or enqueue is called."""
        conn = AsyncMock(spec=AsyncConnection)
        # SELECT returns no row.
        sel_result = MagicMock()
        sel_result.mappings.return_value.fetchone.return_value = None
        conn.execute.return_value = sel_result

        await request_login_code(conn, "nobody@example.com")
        # Only one execute call: the SELECT.
        conn.execute.assert_awaited_once()

    async def test_no_op_when_user_inactive(self):
        """When the user exists but is inactive, nothing is inserted/enqueued."""
        conn = AsyncMock(spec=AsyncConnection)
        sel_result = MagicMock()
        sel_result.mappings.return_value.fetchone.return_value = {
            "id": uuid.uuid4(),
            "is_active": False,
        }
        conn.execute.return_value = sel_result

        await request_login_code(conn, "inactive@example.com")
        conn.execute.assert_awaited_once()

    async def test_dev_mode_logs_code_without_enqueue(self) -> None:
        """In development the code is logged; no job row is inserted."""
        from src.core.config import Environment

        conn = AsyncMock(spec=AsyncConnection)
        sel_result = MagicMock()
        sel_result.mappings.return_value.fetchone.return_value = {
            "id": uuid.uuid4(),
            "is_active": True,
        }
        insert_result = MagicMock()
        conn.execute.side_effect = [sel_result, insert_result]

        dev_settings = MagicMock()
        dev_settings.environment = Environment.DEVELOPMENT
        with patch("src.modules.platform.auth.get_onestop_settings", return_value=dev_settings):
            await request_login_code(conn, "active@example.com")

        # SELECT + INSERT login_code only — no job enqueue.
        assert conn.execute.call_count == 2

    async def test_prod_mode_enqueues_email_job(self) -> None:
        """In production the code is enqueued as send_login_email."""
        from src.core.config import Environment

        conn = AsyncMock(spec=AsyncConnection)
        sel_result = MagicMock()
        sel_result.mappings.return_value.fetchone.return_value = {
            "id": uuid.uuid4(),
            "is_active": True,
        }
        insert_result = MagicMock()
        insert_result.scalar_one.return_value = uuid.uuid4()
        conn.execute.side_effect = [sel_result, insert_result, insert_result]

        prod_settings = MagicMock()
        prod_settings.environment = Environment.PRODUCTION
        with patch("src.modules.platform.auth.get_onestop_settings", return_value=prod_settings):
            await request_login_code(conn, "active@example.com")

        # SELECT + INSERT login_code + INSERT job = 3 calls.
        assert conn.execute.call_count == 3


# ---------------------------------------------------------------------------
# verify_login_code
# ---------------------------------------------------------------------------


class TestVerifyLoginCode:
    _code_id = uuid.uuid4()
    _code = "123456"
    _code_hash = _hash_code("123456")

    def _make_conn_for_verify(self, attempts_at_max: bool = False) -> AsyncMock:
        """Set up conn for a normal verify flow."""
        conn = AsyncMock(spec=AsyncConnection)
        # 1. SELECT active code row.
        sel_result = MagicMock()
        sel_result.mappings.return_value.fetchone.return_value = {
            "id": self._code_id,
            "code_hash": self._code_hash,
        }
        # 2. UPDATE attempts.
        upd_result = MagicMock()
        upd_result.rowcount = 0 if attempts_at_max else 1
        # Remaining calls (consumed_at, last_login_at, user SELECT).
        other = MagicMock()
        other.mappings.return_value.fetchone.return_value = None
        conn.execute.side_effect = [sel_result, upd_result, other, other, other]
        return conn

    async def test_locked_when_update_returns_no_rows(self):
        conn = self._make_conn_for_verify(attempts_at_max=True)
        result, user = await verify_login_code(conn, "x@x.com", self._code)
        assert result is VerifyResult.LOCKED
        assert user is None

    async def test_invalid_when_hash_mismatch(self):
        conn = AsyncMock(spec=AsyncConnection)
        sel_result = MagicMock()
        sel_result.mappings.return_value.fetchone.return_value = {
            "id": self._code_id,
            "code_hash": _hash_code("999999"),  # different hash
        }
        upd_result = MagicMock()
        upd_result.rowcount = 1
        conn.execute.side_effect = [sel_result, upd_result]

        result, user = await verify_login_code(conn, "x@x.com", "000000")
        assert result is VerifyResult.INVALID
        assert user is None

    async def test_invalid_when_no_code_found(self):
        conn = AsyncMock(spec=AsyncConnection)
        sel_result = MagicMock()
        sel_result.mappings.return_value.fetchone.return_value = None
        conn.execute.return_value = sel_result

        result, user = await verify_login_code(conn, "x@x.com", "123456")
        assert result is VerifyResult.INVALID
        assert user is None

    async def test_ok_when_hash_matches(self):
        user_id = uuid.uuid4()
        conn = AsyncMock(spec=AsyncConnection)

        sel_result = MagicMock()
        sel_result.mappings.return_value.fetchone.return_value = {
            "id": self._code_id,
            "code_hash": self._code_hash,
        }
        upd_result = MagicMock()
        upd_result.rowcount = 1
        consumed_result = MagicMock()
        login_result = MagicMock()
        user_result = MagicMock()
        user_result.mappings.return_value.fetchone.return_value = {
            "id": user_id,
            "email": "x@x.com",
            "display_name": None,
            "role": "staff",
            "is_active": True,
        }
        conn.execute.side_effect = [
            sel_result,
            upd_result,
            consumed_result,
            login_result,
            user_result,
        ]

        result, user = await verify_login_code(conn, "x@x.com", self._code)
        assert result is VerifyResult.OK
        assert isinstance(user, UserRow)
        assert user.email == "x@x.com"


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------


class TestCreateSession:
    async def test_returns_raw_token_and_session_id(self):
        conn = AsyncMock(spec=AsyncConnection)
        conn.execute.return_value = MagicMock()

        user_id = uuid.uuid4()
        raw_token, session_id = await create_session(conn, user_id, "TestBrowser/1.0")

        assert isinstance(raw_token, str)
        assert len(raw_token) > 0
        assert isinstance(session_id, uuid.UUID)

    async def test_calls_execute_once(self):
        conn = AsyncMock(spec=AsyncConnection)
        conn.execute.return_value = MagicMock()

        await create_session(conn, uuid.uuid4(), None)
        conn.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# lookup_session
# ---------------------------------------------------------------------------


class TestLookupSession:
    async def test_returns_none_when_no_row(self):
        conn = _make_select_conn(None)
        result = await lookup_session(conn, "some_token")
        assert result is None

    async def test_returns_user_row_when_found(self):
        user_id = uuid.uuid4()
        conn = _make_select_conn(
            {
                "id": user_id,
                "email": "a@b.com",
                "display_name": "Alice",
                "role": "staff",
                "is_active": True,
            }
        )
        user = await lookup_session(conn, "valid_token")
        assert isinstance(user, UserRow)
        assert user.email == "a@b.com"
        assert user.display_name == "Alice"


# ---------------------------------------------------------------------------
# revoke_session
# ---------------------------------------------------------------------------


class TestRevokeSession:
    async def test_calls_execute_once(self):
        conn = AsyncMock(spec=AsyncConnection)
        conn.execute.return_value = MagicMock()
        await revoke_session(conn, "raw_token_here")
        conn.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# bootstrap_admin
# ---------------------------------------------------------------------------


class TestBootstrapAdmin:
    async def test_inserts_with_on_conflict_do_nothing(self):
        conn = AsyncMock(spec=AsyncConnection)
        conn.execute.return_value = MagicMock()
        await bootstrap_admin(conn, "admin@example.com")
        conn.execute.assert_awaited_once()
        # Verify the SQL contains ON CONFLICT DO NOTHING.
        sql_text = str(conn.execute.call_args[0][0])
        assert "ON CONFLICT" in sql_text
        assert "DO NOTHING" in sql_text
