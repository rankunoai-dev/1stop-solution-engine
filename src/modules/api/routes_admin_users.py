"""Admin user-management routes for the 1Stop API (R0.9).

Endpoints
---------
GET /api/v1/admin/users
    List all users with per-user session and LLM-call stats.

POST /api/v1/admin/users
    Create a new user.

PATCH /api/v1/admin/users/{user_id}
    Update a user's ``role``, ``is_active``, or ``display_name``.
    Protects against self-deactivation and removing the last admin.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.api.deps import get_db_conn, require_admin, verify_csrf
from src.modules.platform.auth import UserRow
from src.modules.platform.tables import t_users

__all__ = ["router_admin_users"]

router_admin_users = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_VALID_ROLES = {"staff", "admin"}

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_LIST_USERS_SQL = sa.text(
    """
    SELECT
        u.id,
        u.email,
        u.display_name,
        u.role,
        u.is_active,
        u.created_at,
        u.last_login_at,
        COUNT(DISTINCT s.id) FILTER (
            WHERE s.revoked_at IS NULL AND s.expires_at > now()
        ) AS active_sessions,
        COUNT(l.id) AS llm_call_count,
        COALESCE(SUM(l.input_tokens), 0) AS total_input_tokens,
        COALESCE(SUM(l.output_tokens), 0) AS total_output_tokens,
        COALESCE(SUM(l.cost_usd)::numeric, 0)::float AS total_cost_usd,
        MAX(l.created_at) AS last_llm_call_at
    FROM onestop.users u
    LEFT JOIN onestop.sessions s ON s.user_id = u.id
    LEFT JOIN onestop.llm_calls l ON l.session_id = s.id
    GROUP BY
        u.id, u.email, u.display_name, u.role,
        u.is_active, u.created_at, u.last_login_at
    ORDER BY u.created_at DESC
    """
)

_COUNT_OTHER_ADMINS_SQL = sa.text(
    """
    SELECT COUNT(*) FROM onestop.users
    WHERE role = 'admin' AND is_active = true AND id != :target_id
    """
)

# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateUserBody(BaseModel):
    """Body for POST /admin/users."""

    model_config = ConfigDict(extra="forbid")

    email: str
    display_name: str | None = None
    role: str = "staff"


class PatchUserBody(BaseModel):
    """Body for PATCH /admin/users/{user_id}."""

    model_config = ConfigDict(extra="forbid")

    is_active: bool | None = None
    role: str | None = None
    display_name: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_dict(row: Any) -> dict[str, Any]:  # noqa: ANN401
    """Convert a mappings row to a JSON-safe dict."""
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "is_active": row["is_active"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "last_login_at": row["last_login_at"].isoformat() if row["last_login_at"] else None,
    }


def _stats_row_to_dict(row: Any) -> dict[str, Any]:  # noqa: ANN401
    """Convert a stats query row to a JSON-safe dict."""
    base = _row_to_dict(row)
    base.update(
        {
            "active_sessions": int(row["active_sessions"]),
            "llm_call_count": int(row["llm_call_count"]),
            "total_input_tokens": int(row["total_input_tokens"]),
            "total_output_tokens": int(row["total_output_tokens"]),
            "total_cost_usd": float(row["total_cost_usd"]),
            "last_llm_call_at": (
                row["last_llm_call_at"].isoformat() if row["last_llm_call_at"] else None
            ),
        }
    )
    return base


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router_admin_users.get("/users")
async def list_users(
    admin: UserRow = Depends(require_admin),
    conn: AsyncConnection = Depends(get_db_conn),
) -> list[dict[str, Any]]:
    """Return all users with per-user session and LLM-call statistics.

    Admin-only endpoint.
    """
    _ = admin
    result = await conn.execute(_LIST_USERS_SQL)
    return [_stats_row_to_dict(row) for row in result.mappings().fetchall()]


@router_admin_users.post("/users", status_code=201)
async def create_user(
    body: CreateUserBody,
    admin: UserRow = Depends(require_admin),
    _csrf: None = Depends(verify_csrf),
    conn: AsyncConnection = Depends(get_db_conn),
) -> dict[str, Any]:
    """Create a new user.

    Returns 409 if the email address is already registered.
    Returns 422 if the ``role`` is not ``staff`` or ``admin``.
    """
    _ = admin
    role = body.role.lower()
    if role not in _VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(_VALID_ROLES)}")

    # Check for duplicate email.
    dup = await conn.execute(sa.select(t_users.c.id).where(t_users.c.email == body.email.lower()))
    if dup.fetchone() is not None:
        raise HTTPException(status_code=409, detail="Email already registered.")

    new_id = uuid.uuid4()
    await conn.execute(
        sa.insert(t_users).values(
            id=new_id,
            email=body.email.lower(),
            display_name=body.display_name,
            role=role,
        )
    )
    row = await conn.execute(
        sa.select(
            t_users.c.id,
            t_users.c.email,
            t_users.c.display_name,
            t_users.c.role,
            t_users.c.is_active,
            t_users.c.created_at,
            t_users.c.last_login_at,
        ).where(t_users.c.id == new_id)
    )
    return _row_to_dict(row.mappings().one())


@router_admin_users.patch("/users/{user_id}")
async def patch_user(
    user_id: uuid.UUID,
    body: PatchUserBody,
    admin: UserRow = Depends(require_admin),
    _csrf: None = Depends(verify_csrf),
    conn: AsyncConnection = Depends(get_db_conn),
) -> dict[str, Any]:
    """Update a user's role, active state, or display name.

    Guards:
    - Cannot deactivate your own account.
    - Cannot deactivate or demote the last active admin.
    """
    # Validate role if provided.
    if body.role is not None and body.role not in _VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(_VALID_ROLES)}")

    # Fetch the target user.
    target_sel = await conn.execute(
        sa.select(
            t_users.c.id,
            t_users.c.role,
            t_users.c.is_active,
        ).where(t_users.c.id == user_id)
    )
    target_row = target_sel.mappings().fetchone()
    if target_row is None:
        raise HTTPException(status_code=404, detail="User not found.")

    target_id: uuid.UUID = uuid.UUID(str(target_row["id"]))
    target_is_admin: bool = target_row["role"] == "admin"

    # Guard: cannot deactivate self.
    if body.is_active is False and target_id == admin.id:
        raise HTTPException(status_code=422, detail="Cannot deactivate your own account.")

    # Guard: cannot remove the last admin.
    will_lose_admin = target_is_admin and (
        body.is_active is False or (body.role is not None and body.role != "admin")
    )
    if will_lose_admin:
        count_result = await conn.execute(_COUNT_OTHER_ADMINS_SQL, {"target_id": target_id})
        remaining: int = int(count_result.scalar_one())
        if remaining == 0:
            raise HTTPException(
                status_code=422,
                detail="Cannot deactivate or demote the last active admin.",
            )

    # Build the update values.
    values: dict[str, Any] = {}
    if body.is_active is not None:
        values["is_active"] = body.is_active
    if body.role is not None:
        values["role"] = body.role
    if body.display_name is not None:
        values["display_name"] = body.display_name

    if values:
        await conn.execute(sa.update(t_users).where(t_users.c.id == user_id).values(**values))

    updated = await conn.execute(
        sa.select(
            t_users.c.id,
            t_users.c.email,
            t_users.c.display_name,
            t_users.c.role,
            t_users.c.is_active,
            t_users.c.created_at,
            t_users.c.last_login_at,
        ).where(t_users.c.id == user_id)
    )
    return _row_to_dict(updated.mappings().one())
