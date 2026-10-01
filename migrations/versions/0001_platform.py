"""Platform tables: extensions, schema, and all R0 tables.

Creates the ``onestop`` schema and the eleven platform tables described in
ARCHITECTURE §4.2 (R0 = migration 0001).  Knowledge tables (tools, documents,
chunks, …) arrive in migration 0002 (R1).

Raw SQL is used throughout so Postgres-specific features (GENERATED ALWAYS,
citext, uuid[] arrays, interval, bigint identity) are expressed exactly.

Revision ID: 0001
Revises: —
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create extensions, schema, and platform tables; seed fixed rows."""
    # ------------------------------------------------------------------
    # Extensions (superuser privilege required; pgvector/pgvector image
    # grants it to the owner of the default database).
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Schema is created by env.py before migrations run, but we repeat the
    # guard here so the migration is self-contained.
    op.execute("CREATE SCHEMA IF NOT EXISTS onestop")

    # ------------------------------------------------------------------
    # spaces — one row per knowledge space (seeded with "internal").
    # All content and conversation tables carry space_id so external
    # spaces can be added later without restructuring (D-03).
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE onestop.spaces (
            id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            slug       text        NOT NULL,
            name       text        NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_spaces_slug UNIQUE (slug)
        )
        """
    )

    # ------------------------------------------------------------------
    # users — keyed by email (citext) so Microsoft Entra ID maps onto
    # the same row later by matching on lower-cased email (D-21).
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE onestop.users (
            id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            email         citext      NOT NULL,
            display_name  text,
            role          text        NOT NULL DEFAULT 'staff'
                              CHECK (role IN ('staff', 'admin')),
            is_active     bool        NOT NULL DEFAULT true,
            created_at    timestamptz NOT NULL DEFAULT now(),
            last_login_at timestamptz,
            CONSTRAINT uq_users_email UNIQUE (email)
        )
        """
    )

    # ------------------------------------------------------------------
    # login_codes — 6-digit OTP, stored as a bcrypt/scrypt hash, max 5
    # attempts, 10-minute expiry (auth module R0.9).
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE onestop.login_codes (
            id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            email       citext      NOT NULL,
            code_hash   text        NOT NULL,
            expires_at  timestamptz NOT NULL,
            attempts    smallint    NOT NULL DEFAULT 0,
            consumed_at timestamptz,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # Only index active (unconsumed, unexpired) codes; the lookup is by email.
    op.execute(
        """
        CREATE INDEX idx_login_codes_active
            ON onestop.login_codes (email, expires_at)
         WHERE consumed_at IS NULL
        """
    )

    # ------------------------------------------------------------------
    # sessions — server-side; the session token itself is a 256-bit
    # random value stored outside the DB (cookie / header); only its
    # SHA-256 hash is kept here so sessions can be revoked.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE onestop.sessions (
            id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    uuid        NOT NULL REFERENCES onestop.users(id),
            token_hash text        NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            user_agent text,
            CONSTRAINT uq_sessions_token_hash UNIQUE (token_hash)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_sessions_active
            ON onestop.sessions (token_hash)
         WHERE revoked_at IS NULL
        """
    )

    # ------------------------------------------------------------------
    # llm_calls — unified spend ledger AND LLM trace (D-22, ADR 0005).
    # The ``day`` column is generated so daily cap queries hit an index
    # without a full scan.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE onestop.llm_calls (
            id                  uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at          timestamptz    NOT NULL DEFAULT now(),
            day                 date           NOT NULL
                                    GENERATED ALWAYS AS (created_at::date) STORED,
            purpose             text           NOT NULL
                                    CHECK (purpose IN (
                                        'answer', 'card_draft', 'faq_extract',
                                        'judge', 'eval'
                                    )),
            provider            text           NOT NULL,
            model               text           NOT NULL,
            prompt_version      text,
            input_tokens        int            NOT NULL DEFAULT 0,
            output_tokens       int            NOT NULL DEFAULT 0,
            cost_usd            numeric(10,6)  NOT NULL DEFAULT 0,
            latency_ms          int,
            status              text           NOT NULL DEFAULT 'ok'
                                    CHECK (status IN ('ok', 'error', 'cap_reached')),
            trace_id            text,
            conversation_id     uuid,
            message_id          uuid,
            retrieved_chunk_ids uuid[],
            error               text
        )
        """
    )
    op.execute("CREATE INDEX idx_llm_calls_day ON onestop.llm_calls (day)")
    op.execute("CREATE INDEX idx_llm_calls_purpose_day ON onestop.llm_calls (purpose, day)")

    # ------------------------------------------------------------------
    # jobs — async work queue with FOR UPDATE SKIP LOCKED (D-19, ADR 0003).
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE onestop.jobs (
            id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            kind             text        NOT NULL,
            payload          jsonb       NOT NULL DEFAULT '{}',
            status           text        NOT NULL DEFAULT 'queued'
                                 CHECK (status IN (
                                     'queued', 'running', 'succeeded', 'failed', 'dead'
                                 )),
            run_after        timestamptz NOT NULL DEFAULT now(),
            attempts         int         NOT NULL DEFAULT 0,
            max_attempts     int         NOT NULL DEFAULT 3,
            locked_by        text,
            locked_at        timestamptz,
            last_error       text,
            idempotency_key  text,
            created_at       timestamptz NOT NULL DEFAULT now(),
            finished_at      timestamptz,
            CONSTRAINT uq_jobs_idempotency_key UNIQUE (idempotency_key)
        )
        """
    )
    # The worker polls this index: pending/failed jobs ordered by when to run.
    op.execute(
        """
        CREATE INDEX idx_jobs_claimable
            ON onestop.jobs (status, run_after)
         WHERE status IN ('queued', 'failed')
        """
    )

    # ------------------------------------------------------------------
    # schedules — named recurring jobs; the scheduler enqueues them once
    # per interval with a deterministic idempotency_key (ADR 0003).
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE onestop.schedules (
            name         text        PRIMARY KEY,
            interval     interval    NOT NULL,
            next_run_at  timestamptz NOT NULL,
            last_run_at  timestamptz,
            enabled      bool        NOT NULL DEFAULT true
        )
        """
    )

    # ------------------------------------------------------------------
    # rate_limits — fixed-window counters (login attempts, chat requests).
    # One upsert increments the counter atomically (R0.5).
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE onestop.rate_limits (
            key          text        NOT NULL,
            window_start timestamptz NOT NULL,
            count        int         NOT NULL DEFAULT 0,
            PRIMARY KEY (key, window_start)
        )
        """
    )

    # ------------------------------------------------------------------
    # email_deliveries — idempotent send records; the same
    # idempotency_key is never delivered twice (newsletter-rankuno pattern).
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE onestop.email_deliveries (
            id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            idempotency_key  text        NOT NULL,
            to_email         text        NOT NULL,
            template         text        NOT NULL,
            status           text        NOT NULL DEFAULT 'pending'
                                 CHECK (status IN ('pending', 'sent', 'failed')),
            sent_at          timestamptz,
            error            text,
            created_at       timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_email_deliveries_idempotency_key UNIQUE (idempotency_key)
        )
        """
    )

    # ------------------------------------------------------------------
    # audit_log — append-only; bigint identity so rows are always in
    # insertion order even if clock skew causes out-of-order created_at.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE onestop.audit_log (
            id            bigint      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            at            timestamptz NOT NULL DEFAULT now(),
            actor_user_id uuid        REFERENCES onestop.users(id),
            action        text        NOT NULL,
            target        text        NOT NULL,
            detail        jsonb       NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute("CREATE INDEX idx_audit_log_at ON onestop.audit_log (at)")
    op.execute(
        """
        CREATE INDEX idx_audit_log_actor
            ON onestop.audit_log (actor_user_id)
         WHERE actor_user_id IS NOT NULL
        """
    )

    # ------------------------------------------------------------------
    # settings_kv — runtime-editable values (spend caps, allowlist tweaks).
    # Changes made here are picked up by the admin UI; the settings module
    # provides a typed overlay on top.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE onestop.settings_kv (
            key        text        PRIMARY KEY,
            value      jsonb       NOT NULL,
            updated_by uuid        REFERENCES onestop.users(id),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    # ------------------------------------------------------------------
    # Seed rows: the single internal space and the two built-in schedules.
    # ON CONFLICT DO NOTHING makes re-running upgrade() safe.
    # ------------------------------------------------------------------
    op.execute(
        """
        INSERT INTO onestop.spaces (slug, name)
        VALUES ('internal', 'RankUno Internal')
        ON CONFLICT (slug) DO NOTHING
        """
    )
    # weekly_sync: Sunday 20:30 UTC = Monday 02:00 IST (ADR 0004).
    # housekeeping: daily at midnight UTC.
    op.execute(
        """
        INSERT INTO onestop.schedules (name, interval, next_run_at)
        VALUES
            ('weekly_sync',
             '7 days'::interval,
             date_trunc('week', now() + interval '7 days') + interval '20:30:00'),
            ('housekeeping',
             '1 day'::interval,
             date_trunc('day', now() + interval '1 day'))
        ON CONFLICT (name) DO NOTHING
        """
    )


def downgrade() -> None:
    """Drop all platform tables, then the schema and extensions."""
    # Tables in reverse dependency order.
    for table in (
        "settings_kv",
        "audit_log",
        "email_deliveries",
        "rate_limits",
        "schedules",
        "jobs",
        "llm_calls",
        "sessions",
        "login_codes",
        "users",
        "spaces",
    ):
        op.execute(f"DROP TABLE IF EXISTS onestop.{table} CASCADE")

    op.execute("DROP SCHEMA IF EXISTS onestop CASCADE")

    # Leave extensions in place: they may be used by other projects on the
    # same Postgres instance.  To remove: drop them manually after downgrade.
