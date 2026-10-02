"""1Stop management CLI (R0.11).

Available commands::

    onestop serve [--host HOST] [--port PORT] [--reload]
    onestop migrate
    onestop worker [--kinds KIND,KIND,…]
    onestop sync-now

Use ``onestop --help`` or ``onestop <command> --help`` for details.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

import click
import uvicorn

__all__ = ["cli"]


@click.group()
def cli() -> None:
    """1Stop management commands."""


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host.")  # noqa: S104
@click.option("--port", default=8000, type=int, help="Bind port.")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload.")
def serve(host: str, port: int, reload: bool) -> None:
    """Start the API server."""
    uvicorn.run("src.modules.api.app:app", host=host, port=port, reload=reload)


@cli.command()
def migrate() -> None:
    """Run database migrations (alembic upgrade head)."""
    result = subprocess.run(["alembic", "upgrade", "head"], check=False)  # noqa: S603, S607
    sys.exit(result.returncode)


@cli.command()
@click.option(
    "--kinds",
    default="send_login_email,spend_alert",
    help="Comma-separated job kinds to handle.",
)
def worker(kinds: str) -> None:
    """Start the background worker loop."""
    from src.modules.platform.worker import WorkerLoop  # noqa: PLC0415

    loop = WorkerLoop(kinds=kinds.split(","))
    asyncio.run(loop.run_until_stopped())


@cli.command(name="sync-now")
def sync_now() -> None:
    """Trigger an immediate tool registry sync (enqueues a job)."""
    import uuid  # noqa: PLC0415

    from src.modules.platform.db import transaction  # noqa: PLC0415
    from src.modules.platform.jobs import enqueue  # noqa: PLC0415

    async def _run() -> None:
        async with transaction() as conn:
            job_id = await enqueue(
                conn,
                "registry.sync",
                {},
                idempotency_key=f"manual:{uuid.uuid4()}",
            )
        click.echo(f"Enqueued registry.sync job {job_id}")

    asyncio.run(_run())
