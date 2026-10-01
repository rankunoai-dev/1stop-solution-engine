"""Unit tests for src.modules.platform.db.

These tests exercise the URL conversion helper and the engine lifecycle
without touching a real database.
"""

from __future__ import annotations

import pytest

from src.modules.platform.db import _to_async_url, get_engine, reset_engine


class TestToAsyncUrl:
    """_to_async_url converts every supported sync dialect to the async form."""

    def test_psycopg_sync_prefix_converted(self):
        url = "postgresql+psycopg://user:pass@localhost:5432/db"
        assert _to_async_url(url) == "postgresql+psycopg_async://user:pass@localhost:5432/db"

    def test_bare_postgresql_prefix_converted(self):
        url = "postgresql://user:pass@localhost/db"
        assert _to_async_url(url) == "postgresql+psycopg_async://user:pass@localhost/db"

    def test_postgres_alias_converted(self):
        url = "postgres://user:pass@localhost/db"
        assert _to_async_url(url) == "postgresql+psycopg_async://user:pass@localhost/db"

    def test_already_async_unchanged(self):
        url = "postgresql+psycopg_async://user:pass@localhost/db"
        assert _to_async_url(url) == url

    def test_unknown_dialect_unchanged(self):
        url = "sqlite:///./test.db"
        assert _to_async_url(url) == url

    def test_preserves_query_string(self):
        url = "postgresql+psycopg://u:p@h/db?sslmode=require"
        result = _to_async_url(url)
        assert result == "postgresql+psycopg_async://u:p@h/db?sslmode=require"


class TestGetEngine:
    """get_engine raises when DATABASE_URL is not configured."""

    def test_raises_config_error_without_database_url(self, monkeypatch):
        """get_engine must raise ConfigurationError, not AttributeError."""
        from src.core.errors import ConfigurationError

        monkeypatch.setenv("DATABASE_URL", "")
        # The autouse fixture already reset the engine; ensure it's None.
        reset_engine()
        with pytest.raises(ConfigurationError, match="DATABASE_URL"):
            get_engine()
