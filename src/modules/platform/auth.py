"""Authentication helpers: OTP login codes, sessions, CSRF tokens (R0.9).

Flow
----
1. ``request_login_code`` — generate a 6-digit OTP, hash it with SHA-256,
   insert into ``login_codes``, and enqueue a ``send_login_email`` job.
   The function always returns ``None`` to prevent email enumeration.
2. ``verify_login_code`` — atomically increment attempt count; compare the
   hash; return ``(VerifyResult, UserRow | None)``.
3. ``create_session`` — store a SHA-256 hash of a 48-byte random token.
   Returns the raw token (goes into the browser cookie) and the session id.
4. ``lookup_session`` — hash the raw token, join to users, check validity.
5. ``revoke_session`` — stamp ``revoked_at``.
6. ``generate_csrf_token`` / ``check_csrf_token`` — HMAC-SHA256 bound to the
   session token; constant-time comparison.
7. ``bootstrap_admin`` — idempotent upsert of the initial admin user.

Security notes
--------------
- OTP hashes use SHA-256 (fast; 6-digit OTPs are short-lived and rate-limited).
- Session tokens are 48-byte URL-safe random values (384 bits entropy).
- CSRF tokens are ``HMAC-SHA256(session_token, session_secret)`` so they are
  bound to the session without requiring a separate DB lookup.
- ``check_csrf_token`` uses ``hmac.compare_digest`` for constant-time equality.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.core.config import Environment
from src.modules.platform.jobs import enqueue
from src.modules.platform.settings import get_onestop_settings
from src.modules.platform.tables import t_login_codes, t_sessions, t_users

_logger = logging.getLogger(__name__)

__all__ = [
    "UserRow",
    "VerifyResult",
    "bootstrap_admin",
    "check_csrf_token",
    "create_session",
    "generate_csrf_token",
    "lookup_session",
    "request_login_code",
    "revoke_session",
    "verify_login_code",
]

_OTP_EXPIRY_MINUTES = 10
_SESSION_EXPIRY_DAYS = 30
_MAX_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class UserRow:
    """Projection of the ``users`` table used across the auth boundary."""

    id: uuid.UUID
    email: str
    display_name: str | None
    role: str  # 'staff' | 'admin'
    is_active: bool


class VerifyResult(Enum):
    """Outcome of a login-code verification attempt."""

    OK = "ok"
    INVALID = "invalid"  # wrong code OR no active code found
    EXPIRED = "expired"  # code past its expiry window (currently unused: see docstring)
    LOCKED = "locked"  # >= 5 attempts


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _generate_otp() -> str:
    """Return a cryptographically random 6-digit string (zero-padded)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_code(code: str) -> str:
    """Return the hex SHA-256 digest of *code*."""
    return hashlib.sha256(code.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def request_login_code(conn: AsyncConnection, email: str) -> None:
    """Generate and persist a login OTP for *email* if the account is active.

    The OTP is always generated and hashed (to normalise timing), but the
    ``login_codes`` row and the email job are only created when the user exists
    and ``is_active`` is true.  The function always returns ``None`` so callers
    cannot distinguish a found vs. not-found email address.

    Args:
        conn: Open ``AsyncConnection`` inside an active transaction.
        email: The email address to send the OTP to.
    """
    code = _generate_otp()
    code_hash = _hash_code(code)  # always hash, normalises timing

    # Look up the user; only insert if active.
    result = await conn.execute(
        sa.select(t_users.c.id, t_users.c.is_active).where(t_users.c.email == email)
    )
    row = result.mappings().fetchone()
    if row is None or not row["is_active"]:
        return

    expires_at = datetime.now(UTC) + timedelta(minutes=_OTP_EXPIRY_MINUTES)
    await conn.execute(
        sa.insert(t_login_codes).values(
            email=email,
            code_hash=code_hash,
            expires_at=expires_at,
        )
    )
    if get_onestop_settings().environment is Environment.DEVELOPMENT:
        # In development there is no SMTP configured; print the code so the
        # owner can log in without email.  Never do this in production.
        _logger.warning(
            "\n\n  *** DEV – login code for %s: %s  (expires in %d min) ***\n",
            email,
            code,
            _OTP_EXPIRY_MINUTES,
        )
    else:
        await enqueue(
            conn,
            "send_login_email",
            {"email": email, "code": code},
        )


async def verify_login_code(
    conn: AsyncConnection,
    email: str,
    code: str,
) -> tuple[VerifyResult, UserRow | None]:
    """Verify *code* against the most recent active OTP for *email*.

    The lookup selects only unconsumed, unexpired codes so the INVALID result
    covers both "no code exists" and "code has expired" — preventing callers
    from distinguishing the two.

    The attempt counter is incremented atomically before the hash comparison.
    If the counter already reached :data:`_MAX_ATTEMPTS` the DB update returns
    no rows and the function returns ``LOCKED`` immediately.

    Args:
        conn: Open ``AsyncConnection`` inside an active transaction.
        email: Email to look up.
        code: The raw 6-digit OTP submitted by the user.

    Returns:
        A ``(VerifyResult, UserRow | None)`` tuple.  ``UserRow`` is set only
        when the result is ``OK``.
    """
    # 1. Find the most recent active (unconsumed + not expired) code.
    sel = await conn.execute(
        sa.select(t_login_codes.c.id, t_login_codes.c.code_hash)
        .where(
            t_login_codes.c.email == email,
            t_login_codes.c.consumed_at.is_(None),
            t_login_codes.c.expires_at > sa.text("now()"),
        )
        .order_by(t_login_codes.c.created_at.desc())
        .limit(1)
    )
    code_row = sel.mappings().fetchone()
    if code_row is None:
        return VerifyResult.INVALID, None

    code_id: uuid.UUID = uuid.UUID(str(code_row["id"]))

    # 2. Atomically increment attempts; guard blocks at >= _MAX_ATTEMPTS.
    upd = await conn.execute(
        sa.text(
            "UPDATE onestop.login_codes"
            " SET attempts = attempts + 1"
            " WHERE id = :id AND attempts < :max_attempts"
            " RETURNING id, code_hash"
        ),
        {"id": code_id, "max_attempts": _MAX_ATTEMPTS},
    )
    if upd.rowcount == 0:
        return VerifyResult.LOCKED, None

    # 3. Compare the submitted code's hash.
    stored_hash: str = str(code_row["code_hash"])
    if not hmac.compare_digest(_hash_code(code), stored_hash):
        return VerifyResult.INVALID, None

    # 4. Mark the code consumed and refresh the user's last_login_at.
    await conn.execute(
        sa.update(t_login_codes)
        .where(t_login_codes.c.id == code_id)
        .values(consumed_at=sa.text("now()"))
    )
    await conn.execute(
        sa.update(t_users).where(t_users.c.email == email).values(last_login_at=sa.text("now()"))
    )

    # 5. Fetch the user row.
    user_sel = await conn.execute(
        sa.select(
            t_users.c.id,
            t_users.c.email,
            t_users.c.display_name,
            t_users.c.role,
            t_users.c.is_active,
        ).where(t_users.c.email == email)
    )
    user_row = user_sel.mappings().fetchone()
    if user_row is None:
        return VerifyResult.INVALID, None

    user = UserRow(
        id=uuid.UUID(str(user_row["id"])),
        email=str(user_row["email"]),
        display_name=str(user_row["display_name"]) if user_row["display_name"] else None,
        role=str(user_row["role"]),
        is_active=bool(user_row["is_active"]),
    )
    return VerifyResult.OK, user


async def create_session(
    conn: AsyncConnection,
    user_id: uuid.UUID,
    user_agent: str | None,
    *,
    days: int = _SESSION_EXPIRY_DAYS,
) -> tuple[str, uuid.UUID]:
    """Create a new session and return ``(raw_token, session_id)``.

    The raw token is a 48-byte URL-safe random value that goes into the
    browser cookie.  Only its SHA-256 hash is stored in the database.

    Args:
        conn: Open ``AsyncConnection`` inside an active transaction.
        user_id: UUID of the authenticated user.
        user_agent: ``User-Agent`` request header, or ``None``.
        days: How many days until the session expires.

    Returns:
        A ``(raw_token, session_id)`` tuple.
    """
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_code(raw_token)
    session_id = uuid.uuid4()
    expires_at = datetime.now(UTC) + timedelta(days=days)

    await conn.execute(
        sa.insert(t_sessions).values(
            id=session_id,
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
        )
    )
    return raw_token, session_id


_LOOKUP_SESSION_SQL = sa.text(
    """
    SELECT u.id, u.email, u.display_name, u.role, u.is_active
    FROM onestop.sessions s
    JOIN onestop.users u ON u.id = s.user_id
    WHERE s.token_hash = :token_hash
      AND s.revoked_at IS NULL
      AND s.expires_at > now()
      AND u.is_active = true
    """
)


async def lookup_session(conn: AsyncConnection, raw_token: str) -> UserRow | None:
    """Return the active user for *raw_token*, or ``None`` if not found/valid.

    Checks: token hash match, not revoked, not expired, user is active.

    Args:
        conn: Open ``AsyncConnection``.
        raw_token: The raw session token from the browser cookie/header.
    """
    token_hash = _hash_code(raw_token)
    result = await conn.execute(_LOOKUP_SESSION_SQL, {"token_hash": token_hash})
    row = result.mappings().fetchone()
    if row is None:
        return None
    return UserRow(
        id=uuid.UUID(str(row["id"])),
        email=str(row["email"]),
        display_name=str(row["display_name"]) if row["display_name"] else None,
        role=str(row["role"]),
        is_active=bool(row["is_active"]),
    )


async def revoke_session(conn: AsyncConnection, raw_token: str) -> None:
    """Stamp ``revoked_at`` on the session identified by *raw_token*.

    Args:
        conn: Open ``AsyncConnection`` inside an active transaction.
        raw_token: The raw session token from the browser cookie/header.
    """
    token_hash = _hash_code(raw_token)
    await conn.execute(
        sa.update(t_sessions)
        .where(t_sessions.c.token_hash == token_hash)
        .values(revoked_at=sa.text("now()"))
    )


def generate_csrf_token(raw_session_token: str, secret: str) -> str:
    """Return an HMAC-SHA256 token bound to *raw_session_token*.

    The token is a hex digest of ``HMAC(key=secret, msg=raw_session_token,
    digestmod=sha256)``.  It must be sent back in the ``X-CSRF-Token`` header
    for mutating requests.

    Args:
        raw_session_token: The raw session token (not the hash).
        secret: The ``SESSION_SECRET`` value from settings.
    """
    return hmac.new(secret.encode(), raw_session_token.encode(), hashlib.sha256).hexdigest()


def check_csrf_token(token: str, raw_session_token: str, secret: str) -> bool:
    """Return ``True`` if *token* matches the expected CSRF token.

    Uses ``hmac.compare_digest`` for constant-time comparison to prevent
    timing-based attacks.

    Args:
        token: The ``X-CSRF-Token`` header value submitted by the client.
        raw_session_token: The raw session token from the cookie/header.
        secret: The ``SESSION_SECRET`` value from settings.
    """
    expected = generate_csrf_token(raw_session_token, secret)
    return hmac.compare_digest(token, expected)


async def bootstrap_admin(conn: AsyncConnection, email: str) -> None:
    """Insert an admin user with *email* if no user with that email exists.

    Uses ``ON CONFLICT (email) DO NOTHING`` so it is safe to call on every
    startup without duplicating the row.

    Args:
        conn: Open ``AsyncConnection`` inside an active transaction.
        email: Lower-cased email address for the bootstrap admin.
    """
    await conn.execute(
        sa.text(
            "INSERT INTO onestop.users (email, role, is_active)"
            " VALUES (:email, 'admin', true)"
            " ON CONFLICT (email) DO NOTHING"
        ),
        {"email": email},
    )
