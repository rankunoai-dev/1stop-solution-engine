"""Admin job-queue routes (R0.11, ARCHITECTURE D-19).

Endpoints
---------
GET /api/v1/admin/jobs
    List recent job rows (no raw payload for security).

POST /api/v1/admin/jobs/{job_id}/retry
    Reset a ``dead`` or ``failed`` job to ``queued`` so the worker will
    pick it up again on the next poll.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.api.deps import get_db_conn, require_admin, verify_csrf
from src.modules.platform.auth import UserRow
from src.modules.platform.tables import t_jobs

__all__ = ["router_admin_jobs"]

router_admin_jobs = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_LIST_JOBS_SQL = sa.text(
    """
    SELECT
        id,
        kind,
        status,
        attempts,
        max_attempts,
        run_after,
        locked_at,
        created_at,
        CASE WHEN payload IS NOT NULL THEN true ELSE false END AS has_payload,
        last_error AS error
    FROM onestop.jobs
    WHERE (:status IS NULL OR status = :status)
    ORDER BY created_at DESC
    LIMIT :limit
    """
)


@router_admin_jobs.get("/jobs")
async def list_jobs(
    status: str | None = None,
    limit: int = 50,
    admin: UserRow = Depends(require_admin),
    conn: AsyncConnection = Depends(get_db_conn),
) -> list[dict[str, Any]]:
    """Return a page of recent job rows without raw payloads.

    Args:
        status: Optional status filter (``queued``, ``running``, ``failed``,
            ``succeeded``, ``dead``).  All statuses when omitted.
        limit: Maximum number of rows returned (capped at 200).
        admin: Admin-only endpoint.
        conn: Database connection.

    Returns:
        A list of job summary dicts.
    """
    _ = admin
    effective_limit = min(limit, 200)
    result = await conn.execute(
        _LIST_JOBS_SQL,
        {"status": status, "limit": effective_limit},
    )
    return [
        {
            "id": str(row["id"]),
            "kind": row["kind"],
            "status": row["status"],
            "attempts": int(row["attempts"]),
            "max_attempts": int(row["max_attempts"]),
            "run_after": row["run_after"].isoformat() if row["run_after"] else None,
            "locked_at": row["locked_at"].isoformat() if row["locked_at"] else None,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "has_payload": bool(row["has_payload"]),
            "error": row["error"],
        }
        for row in result.mappings().fetchall()
    ]


@router_admin_jobs.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: uuid.UUID,
    admin: UserRow = Depends(require_admin),
    _csrf: None = Depends(verify_csrf),
    conn: AsyncConnection = Depends(get_db_conn),
) -> dict[str, Any]:
    """Reset a ``dead`` or ``failed`` job to ``queued`` for immediate retry.

    Clears the error, resets the attempt counter to 0, and sets
    ``run_after`` to now so the next worker poll picks it up.

    Args:
        job_id: UUID of the job to retry.
        admin: Admin-only endpoint.
        _csrf: CSRF validation side-effect.
        conn: Database connection inside an active transaction.

    Returns:
        Updated job summary dict.

    Raises:
        HTTPException: 404 if the job does not exist.
        HTTPException: 422 if the job is not in a retryable state.
    """
    _ = admin
    sel = await conn.execute(
        sa.select(
            t_jobs.c.id,
            t_jobs.c.kind,
            t_jobs.c.status,
            t_jobs.c.attempts,
            t_jobs.c.max_attempts,
            t_jobs.c.run_after,
            t_jobs.c.locked_at,
            t_jobs.c.created_at,
            t_jobs.c.last_error,
        ).where(t_jobs.c.id == job_id)
    )
    row = sel.mappings().fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    current_status: str = str(row["status"])
    if current_status not in ("dead", "failed"):
        raise HTTPException(
            status_code=422,
            detail=f"Job cannot be retried from status '{current_status}'. "
            "Only 'dead' or 'failed' jobs can be retried.",
        )

    await conn.execute(
        sa.update(t_jobs)
        .where(t_jobs.c.id == job_id)
        .values(
            status="queued",
            attempts=0,
            last_error=None,
            run_after=sa.text("now()"),
            locked_at=None,
            locked_by=None,
            finished_at=None,
        )
    )

    updated = await conn.execute(
        sa.select(
            t_jobs.c.id,
            t_jobs.c.kind,
            t_jobs.c.status,
            t_jobs.c.attempts,
            t_jobs.c.max_attempts,
            t_jobs.c.run_after,
            t_jobs.c.locked_at,
            t_jobs.c.created_at,
            t_jobs.c.last_error,
        ).where(t_jobs.c.id == job_id)
    )
    upd_row = updated.mappings().one()
    return {
        "id": str(upd_row["id"]),
        "kind": upd_row["kind"],
        "status": upd_row["status"],
        "attempts": int(upd_row["attempts"]),
        "max_attempts": int(upd_row["max_attempts"]),
        "run_after": upd_row["run_after"].isoformat() if upd_row["run_after"] else None,
        "locked_at": upd_row["locked_at"].isoformat() if upd_row["locked_at"] else None,
        "created_at": upd_row["created_at"].isoformat() if upd_row["created_at"] else None,
        "error": upd_row["last_error"],
    }
