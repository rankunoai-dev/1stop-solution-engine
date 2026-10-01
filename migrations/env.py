"""Alembic environment: reads DATABASE_URL from settings.

Always uses the sync psycopg3 dialect for migrations regardless of how the
app connects.

Design notes (ARCHITECTURE §4, ADR 0002):
- All application tables live in the ``onestop`` schema.  The ``alembic_version``
  table is also kept there via ``version_table_schema``.
- We write raw SQL migrations (``target_metadata = None``), so Alembic's
  autogenerate feature is intentionally disabled.
- ``NullPool`` is used to keep each migration run to a single connection that
  is released cleanly on exit (important on Railway where connection counts are
  limited).
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

# ---------------------------------------------------------------------------
# Add project root to sys.path so `src.*` can be imported when alembic is
# invoked from the project root (e.g. `alembic upgrade head`).
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ---------------------------------------------------------------------------
# Read Alembic's ini-file logger config (levels only; handlers set above).
# ---------------------------------------------------------------------------
alembic_cfg = context.config
if alembic_cfg.config_file_name is not None:
    fileConfig(alembic_cfg.config_file_name)

# Raw SQL migrations – autogenerate is not used.
target_metadata = None

_ONESTOP_SCHEMA = "onestop"


def _get_sync_url() -> str:
    """Return the sync psycopg3 URL from DATABASE_URL or OneStopSettings.

    The async URL variant (``+psycopg_async://``) is normalised to the sync one
    because Alembic uses synchronous connections.
    """
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        # Fall back to settings (which may in turn read from .env).
        try:
            from src.modules.platform.settings import get_onestop_settings  # noqa: PLC0415

            db = get_onestop_settings().database_url
            if db:
                url = db.get_secret_value()
        except Exception:  # noqa: BLE001,S110 – best-effort; error surfaced below
            pass

    if not url:
        msg = "DATABASE_URL is not set. Export it or add it to .env before running Alembic."
        raise RuntimeError(msg)

    # Ensure synchronous dialect for migrations.
    return url.replace("+psycopg_async://", "+psycopg://")


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live database connection.

    Useful for generating a migration script to review before applying it.
    """
    url = _get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=_ONESTOP_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    url = _get_sync_url()
    engine = create_engine(url, poolclass=pool.NullPool)

    with engine.connect() as connection:
        # Ensure the schema exists and set the search path so extension-created
        # functions (e.g. gen_random_uuid) are reachable without qualification.
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {_ONESTOP_SCHEMA}"))
        connection.execute(text(f"SET search_path TO {_ONESTOP_SCHEMA}, public"))
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=_ONESTOP_SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
