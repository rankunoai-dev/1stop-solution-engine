"""Unit tests for src.modules.platform.tables.

Verifies that every platform table is defined and carries the expected columns,
without connecting to a database.  Presence of columns here gives us confidence
that the migration and the Python schema are in sync for the columns that matter
most to application code.
"""

from __future__ import annotations

import sqlalchemy as sa

from src.modules.platform.tables import (
    metadata,
    t_audit_log,
    t_email_deliveries,
    t_jobs,
    t_llm_calls,
    t_login_codes,
    t_rate_limits,
    t_schedules,
    t_sessions,
    t_settings_kv,
    t_spaces,
    t_users,
)


class TestMetadata:
    def test_schema_is_onestop(self):
        assert metadata.schema == "onestop"

    def test_all_eleven_tables_registered(self):
        expected = {
            "spaces",
            "users",
            "login_codes",
            "sessions",
            "llm_calls",
            "jobs",
            "schedules",
            "rate_limits",
            "email_deliveries",
            "audit_log",
            "settings_kv",
        }
        # metadata.tables keys are "schema.table_name"
        names = {t.split(".", 1)[-1] for t in metadata.tables}
        assert names == expected


class TestSpaces:
    def test_primary_key_is_id(self):
        pk = [c.name for c in t_spaces.primary_key]
        assert pk == ["id"]

    def test_required_columns_present(self):
        for col in ("id", "slug", "name", "created_at"):
            assert col in t_spaces.c, f"missing column: {col}"


class TestUsers:
    def test_primary_key_and_core_columns(self):
        assert "id" in t_users.c
        assert "email" in t_users.c
        assert "role" in t_users.c
        assert "is_active" in t_users.c


class TestLoginCodes:
    def test_columns(self):
        for col in ("id", "email", "code_hash", "expires_at", "attempts", "consumed_at"):
            assert col in t_login_codes.c, f"missing: {col}"


class TestSessions:
    def test_columns(self):
        for col in ("id", "user_id", "token_hash", "expires_at", "revoked_at"):
            assert col in t_sessions.c, f"missing: {col}"


class TestLlmCalls:
    def test_columns(self):
        for col in (
            "id",
            "created_at",
            "day",
            "purpose",
            "provider",
            "model",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "status",
        ):
            assert col in t_llm_calls.c, f"missing: {col}"

    def test_cost_usd_is_numeric(self):
        assert isinstance(t_llm_calls.c.cost_usd.type, sa.Numeric)

    def test_retrieved_chunk_ids_is_array(self):
        from sqlalchemy.dialects.postgresql import ARRAY

        assert isinstance(t_llm_calls.c.retrieved_chunk_ids.type, ARRAY)


class TestJobs:
    def test_columns(self):
        for col in (
            "id",
            "kind",
            "payload",
            "status",
            "run_after",
            "attempts",
            "max_attempts",
            "idempotency_key",
        ):
            assert col in t_jobs.c, f"missing: {col}"

    def test_payload_is_jsonb(self):
        from sqlalchemy.dialects.postgresql import JSONB

        assert isinstance(t_jobs.c.payload.type, JSONB)


class TestSchedules:
    def test_primary_key_is_name(self):
        pk = [c.name for c in t_schedules.primary_key]
        assert pk == ["name"]

    def test_interval_column_exists(self):
        assert "interval" in t_schedules.c
        assert isinstance(t_schedules.c.interval.type, sa.Interval)


class TestRateLimits:
    def test_composite_pk(self):
        pk = {c.name for c in t_rate_limits.primary_key}
        assert pk == {"key", "window_start"}


class TestEmailDeliveries:
    def test_idempotency_key_column(self):
        assert "idempotency_key" in t_email_deliveries.c


class TestAuditLog:
    def test_bigint_primary_key(self):
        assert "id" in t_audit_log.c
        assert isinstance(t_audit_log.c.id.type, sa.BigInteger)

    def test_detail_is_jsonb(self):
        from sqlalchemy.dialects.postgresql import JSONB

        assert isinstance(t_audit_log.c.detail.type, JSONB)


class TestSettingsKv:
    def test_primary_key_is_key(self):
        pk = [c.name for c in t_settings_kv.primary_key]
        assert pk == ["key"]

    def test_value_is_jsonb(self):
        from sqlalchemy.dialects.postgresql import JSONB

        assert isinstance(t_settings_kv.c.value.type, JSONB)
