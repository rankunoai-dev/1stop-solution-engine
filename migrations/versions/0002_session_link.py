"""Add session_id FK to llm_calls (R0.9 auth).

Links every LLM call to the session that initiated it, enabling per-user
spend accounting and the admin usage dashboard (ARCHITECTURE S4.2).

The column is nullable so rows inserted before this migration (and rows
inserted without an active session, e.g. background jobs) remain valid.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable session_id FK column and index to llm_calls."""
    op.execute(
        """
        ALTER TABLE onestop.llm_calls
            ADD COLUMN session_id uuid REFERENCES onestop.sessions(id)
        """
    )
    op.execute(
        "CREATE INDEX idx_llm_calls_session_id ON onestop.llm_calls (session_id)"
        " WHERE session_id IS NOT NULL"
    )


def downgrade() -> None:
    """Remove session_id column (and its index via CASCADE)."""
    op.execute("DROP INDEX IF EXISTS onestop.idx_llm_calls_session_id")
    op.execute("ALTER TABLE onestop.llm_calls DROP COLUMN IF EXISTS session_id")
