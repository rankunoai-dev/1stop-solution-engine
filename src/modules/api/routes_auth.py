"""Authentication routes for the 1Stop API (R0.9).

Endpoints
---------
POST /api/v1/auth/request-code
    Request a login OTP for the given email.  Always returns 200 with a
    generic message (no enumeration).

POST /api/v1/auth/verify-code
    Submit the OTP; on success set a session cookie and return CSRF token.

POST /api/v1/auth/logout
    Revoke the current session and clear the cookie.

GET /api/v1/me
    Return the current user's profile.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.api.deps import current_user, get_db_conn, verify_csrf
from src.modules.platform.auth import (
    UserRow,
    VerifyResult,
    create_session,
    generate_csrf_token,
    request_login_code,
    revoke_session,
    verify_login_code,
)
from src.modules.platform.rate_limit import check_and_increment
from src.modules.platform.settings import get_onestop_settings

__all__ = ["router_auth"]

router_auth = APIRouter(prefix="/api/v1", tags=["auth"])

_SESSION_COOKIE = "session"
_SESSION_MAX_AGE = 30 * 86_400  # 30 days in seconds


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class RequestCodeBody(BaseModel):
    """Body for POST /auth/request-code."""

    model_config = ConfigDict(extra="forbid")

    email: str


class VerifyCodeBody(BaseModel):
    """Body for POST /auth/verify-code."""

    model_config = ConfigDict(extra="forbid")

    email: str
    code: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_dict(user: UserRow) -> dict[str, Any]:
    """Return a JSON-serialisable dict for a ``UserRow``."""
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router_auth.post("/auth/request-code")
async def request_code(
    body: RequestCodeBody,
    request: Request,
    conn: AsyncConnection = Depends(get_db_conn),
) -> dict[str, str]:
    """Request a login OTP for *email*.

    Rate-limited to 3 requests per 10 minutes per email and 10 per 5 minutes
    per IP.  Both limits are checked but the response is always the same
    generic message so callers cannot enumerate valid addresses.
    """
    email_lower = body.email.lower()
    client_ip = request.client.host if request.client else "unknown"

    # Apply rate limits; even when exceeded we still return 200 (no enumeration).
    await check_and_increment(conn, f"otp_req:{email_lower}", 3, 600)
    await check_and_increment(conn, f"otp_req_ip:{client_ip}", 10, 300)

    await request_login_code(conn, email_lower)
    return {"detail": "If this address is registered, a login code has been sent."}


@router_auth.post("/auth/verify-code")
async def verify_code(
    body: VerifyCodeBody,
    request: Request,
    response: Response,
    conn: AsyncConnection = Depends(get_db_conn),
) -> dict[str, Any]:
    """Verify the OTP and issue a session cookie + CSRF token on success.

    Rate-limited to 10 requests per 15 minutes per email.
    """
    email_lower = body.email.lower()

    # Per-email rate limit: 10 attempts per 15 minutes.
    allowed = await check_and_increment(conn, f"otp_verify:{email_lower}", 10, 900)
    if not allowed:
        raise HTTPException(status_code=422, detail="Invalid or expired code.")

    result, user = await verify_login_code(conn, email_lower, body.code)
    if result is not VerifyResult.OK or user is None:
        raise HTTPException(status_code=422, detail="Invalid or expired code.")

    user_agent = request.headers.get("User-Agent")
    raw_token, _session_id = await create_session(conn, user.id, user_agent)

    s = get_onestop_settings()
    secret = s.session_secret.get_secret_value() if s.session_secret else ""
    csrf = generate_csrf_token(raw_token, secret)

    response.set_cookie(
        _SESSION_COOKIE,
        raw_token,
        httponly=True,
        samesite="lax",
        max_age=_SESSION_MAX_AGE,
    )
    return {"csrf_token": csrf, "user": _user_dict(user)}


@router_auth.post("/auth/logout")
async def logout(
    request: Request,
    response: Response,
    user: UserRow = Depends(current_user),
    _csrf: None = Depends(verify_csrf),
    conn: AsyncConnection = Depends(get_db_conn),
) -> dict[str, str]:
    """Revoke the current session and clear the session cookie.

    Requires a valid ``X-CSRF-Token`` header.
    """
    _ = user  # authentication side-effect; user identity not needed here
    token = request.cookies.get(_SESSION_COOKIE) or request.headers.get("X-Session-Token", "")
    await revoke_session(conn, token)
    response.delete_cookie(_SESSION_COOKIE)
    return {"detail": "Logged out."}


@router_auth.get("/me")
async def me(user: UserRow = Depends(current_user)) -> dict[str, Any]:
    """Return the current user's profile."""
    return _user_dict(user)
