"""SQLAlchemy Core Table objects for the ``onestop`` schema (ARCHITECTURE S4.2).

These objects are the Python representation of migrations 0001 and 0002's DDL.
They are used to build typed queries in application code; the database schema
itself is the source of truth (managed by Alembic).

Column types use standard SQLAlchemy equivalents where Postgres-specific types
add no Python-side behaviour:

- ``citext``                             -> ``sa.Text()``
- ``uuid[]``                             -> ``postgresql.ARRAY(postgresql.UUID(...))``
- ``interval``                           -> ``sa.Interval()``
- ``bigint GENERATED ALWAYS AS IDENTITY``-> ``sa.BigInteger()`` + ``autoincrement``
- ``jsonb``                              -> ``postgresql.JSONB()``

Migration history:
- 0001: all platform tables (R0.1 – R0.8)
- 0002: session_link — adds ``session_id`` FK to ``llm_calls`` (R0.9)
- 0003: knowledge tables (tools, documents, chunks, …) — R1
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

__all__ = [
    "metadata",
    "t_spaces",
    "t_users",
    "t_login_codes",
    "t_sessions",
    "t_llm_calls",
    "t_jobs",
    "t_schedules",
    "t_rate_limits",
    "t_email_deliveries",
    "t_audit_log",
    "t_settings_kv",
]

# All platform tables live in the ``onestop`` schema.
metadata = sa.MetaData(schema="onestop")

# ---------------------------------------------------------------------------
# Spaces
# ---------------------------------------------------------------------------

t_spaces = sa.Table(
    "spaces",
    metadata,
    sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    ),
    sa.Column("slug", sa.Text(), nullable=False),
    sa.Column("name", sa.Text(), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
)

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

t_users = sa.Table(
    "users",
    metadata,
    sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    ),
    # citext in Postgres; Text in Python -- case matching is DB-side.
    sa.Column("email", sa.Text(), nullable=False),
    sa.Column("display_name", sa.Text()),
    sa.Column("role", sa.Text(), nullable=False, server_default=sa.text("'staff'")),
    sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column("last_login_at", sa.DateTime(timezone=True)),
)

# ---------------------------------------------------------------------------
# Login codes (OTP)
# ---------------------------------------------------------------------------

t_login_codes = sa.Table(
    "login_codes",
    metadata,
    sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    ),
    sa.Column("email", sa.Text(), nullable=False),
    sa.Column("code_hash", sa.Text(), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
    sa.Column("consumed_at", sa.DateTime(timezone=True)),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
)

# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

t_sessions = sa.Table(
    "sessions",
    metadata,
    sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    ),
    sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("token_hash", sa.Text(), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("revoked_at", sa.DateTime(timezone=True)),
    sa.Column("user_agent", sa.Text()),
)

# ---------------------------------------------------------------------------
# LLM calls (spend ledger + trace, D-22, ADR 0005)
# ---------------------------------------------------------------------------

t_llm_calls = sa.Table(
    "llm_calls",
    metadata,
    sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    # ``day`` is a GENERATED ALWAYS AS (created_at::date) STORED column in
    # Postgres; we declare it as a regular column here so Python can read it.
    sa.Column("day", sa.Date(), nullable=False),
    sa.Column("purpose", sa.Text(), nullable=False),
    sa.Column("provider", sa.Text(), nullable=False),
    sa.Column("model", sa.Text(), nullable=False),
    sa.Column("prompt_version", sa.Text()),
    sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.Column(
        "cost_usd",
        sa.Numeric(precision=10, scale=6),
        nullable=False,
        server_default=sa.text("0"),
    ),
    sa.Column("latency_ms", sa.Integer()),
    sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'ok'")),
    sa.Column("trace_id", sa.Text()),
    sa.Column("conversation_id", postgresql.UUID(as_uuid=True)),
    sa.Column("message_id", postgresql.UUID(as_uuid=True)),
    sa.Column(
        "retrieved_chunk_ids",
        postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
    ),
    sa.Column("error", sa.Text()),
    # session_id added by migration 0002 (R0.9): nullable FK to sessions.
    sa.Column("session_id", postgresql.UUID(as_uuid=True)),
)

# ---------------------------------------------------------------------------
# Jobs (async work queue, ADR 0003)
# ---------------------------------------------------------------------------

t_jobs = sa.Table(
    "jobs",
    metadata,
    sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    ),
    sa.Column("kind", sa.Text(), nullable=False),
    sa.Column(
        "payload",
        postgresql.JSONB(),
        nullable=False,
        server_default=sa.text("'{}'"),
    ),
    sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
    sa.Column(
        "run_after",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
    sa.Column("locked_by", sa.Text()),
    sa.Column("locked_at", sa.DateTime(timezone=True)),
    sa.Column("last_error", sa.Text()),
    sa.Column("idempotency_key", sa.Text()),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
)

# ---------------------------------------------------------------------------
# Schedules (named recurring jobs, ADR 0003/0004)
# ---------------------------------------------------------------------------

t_schedules = sa.Table(
    "schedules",
    metadata,
    sa.Column("name", sa.Text(), primary_key=True),
    sa.Column("interval", sa.Interval(), nullable=False),
    sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_run_at", sa.DateTime(timezone=True)),
    sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
)

# ---------------------------------------------------------------------------
# Rate limits (fixed-window counters, R0.5)
# ---------------------------------------------------------------------------

t_rate_limits = sa.Table(
    "rate_limits",
    metadata,
    sa.Column("key", sa.Text(), nullable=False),
    sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
    sa.Column("count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.PrimaryKeyConstraint("key", "window_start"),
)

# ---------------------------------------------------------------------------
# Email deliveries (idempotent send records, R0.8)
# ---------------------------------------------------------------------------

t_email_deliveries = sa.Table(
    "email_deliveries",
    metadata,
    sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    ),
    sa.Column("idempotency_key", sa.Text(), nullable=False),
    sa.Column("to_email", sa.Text(), nullable=False),
    sa.Column("template", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
    sa.Column("sent_at", sa.DateTime(timezone=True)),
    sa.Column("error", sa.Text()),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
)

# ---------------------------------------------------------------------------
# Audit log (append-only, bigint identity primary key, R0.5)
# ---------------------------------------------------------------------------

t_audit_log = sa.Table(
    "audit_log",
    metadata,
    sa.Column(
        "id",
        sa.BigInteger(),
        primary_key=True,
        # GENERATED ALWAYS AS IDENTITY in Postgres.
        # We use autoincrement=True so SQLAlchemy knows it's DB-generated.
        autoincrement=True,
    ),
    sa.Column(
        "at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
    sa.Column("action", sa.Text(), nullable=False),
    sa.Column("target", sa.Text(), nullable=False),
    sa.Column(
        "detail",
        postgresql.JSONB(),
        nullable=False,
        server_default=sa.text("'{}'"),
    ),
)

# ---------------------------------------------------------------------------
# Settings KV (runtime-editable values, R0.5)
# ---------------------------------------------------------------------------

t_settings_kv = sa.Table(
    "settings_kv",
    metadata,
    sa.Column("key", sa.Text(), primary_key=True),
    sa.Column(
        "value",
        postgresql.JSONB(),
        nullable=False,
    ),
    sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
)
