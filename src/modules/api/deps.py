"""FastAPI dependency providers for the 1Stop API (R0.9).

Provides:
- ``get_db_conn``: yields an ``AsyncConnection`` for the current request.
- ``current_user``: resolves the session token to a ``UserRow``; raises 401
  if the token is missing or the session is invalid/expired.
- ``require_admin``: calls ``current_user`` and raises 403 if not an admin.
- ``verify_csrf``: validates the ``X-CSRF-Token`` header; raises 403 on
  failure.  Depends on ``current_user`` so the session is always checked first.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.platform.auth import UserRow, check_csrf_token, lookup_session
from src.modules.platform.db import transaction
from src.modules.platform.settings import get_onestop_settings

__all__ = [
    "current_user",
    "get_db_conn",
    "require_admin",
    "verify_csrf",
]


async def get_db_conn() -> AsyncGenerator[AsyncConnection, None]:
    """Yield an ``AsyncConnection`` for the lifetime of one request.

    The connection is wrapped in a transaction that commits on normal exit and
    rolls back on exception.
    """
    async with transaction() as conn:
        yield conn


async def current_user(
    request: Request,
    conn: AsyncConnection = Depends(get_db_conn),
) -> UserRow:
    """Resolve the session token to the authenticated ``UserRow``.

    Reads the token from the ``session`` cookie first, then the
    ``X-Session-Token`` header as a fallback (for non-browser clients).

    Raises:
        HTTPException: 401 when the token is absent or the session is
            invalid, expired, or for an inactive user.
    """
    token = request.cookies.get("session") or request.headers.get("X-Session-Token", "")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await lookup_session(conn, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return user


async def require_admin(user: UserRow = Depends(current_user)) -> UserRow:
    """Return the current user, raising 403 if they are not an admin.

    Raises:
        HTTPException: 403 when the authenticated user's role is not ``admin``.
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def verify_csrf(
    request: Request,
    user: UserRow = Depends(current_user),
) -> None:
    """Validate the ``X-CSRF-Token`` header for mutating requests.

    The expected token is ``HMAC-SHA256(key=SESSION_SECRET, msg=session_token)``
    as returned by the verify-code endpoint on login.

    Args:
        request: The incoming HTTP request.
        user: Injected via ``current_user`` to ensure authentication runs first.

    Raises:
        HTTPException: 403 when the header is absent or the token is wrong.
        HTTPException: 500 when ``SESSION_SECRET`` is not configured.
    """
    # user is injected to run authentication; it is not used directly here.
    _ = user
    token = request.cookies.get("session") or request.headers.get("X-Session-Token", "")
    csrf_header = request.headers.get("X-CSRF-Token", "")
    if not csrf_header:
        raise HTTPException(status_code=403, detail="CSRF token required")
    s = get_onestop_settings()
    if s.session_secret is None:
        raise HTTPException(status_code=500, detail="Session secret not configured")
    if not check_csrf_token(csrf_header, token, s.session_secret.get_secret_value()):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
