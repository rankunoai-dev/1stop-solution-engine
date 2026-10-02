"""Unit tests for the 1Stop CLI (src/cli.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from src.cli import cli


class TestCliGroup:
    def test_group_exists(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "1Stop management commands" in result.output

    def test_all_commands_registered(self):
        assert "serve" in cli.commands  # type: ignore[attr-defined]
        assert "migrate" in cli.commands  # type: ignore[attr-defined]
        assert "worker" in cli.commands  # type: ignore[attr-defined]
        assert "sync-now" in cli.commands  # type: ignore[attr-defined]


class TestMigrateCommand:
    def test_migrate_calls_alembic(self):
        runner = CliRunner()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["migrate"])
        mock_run.assert_called_once_with(["alembic", "upgrade", "head"], check=False)
        assert result.exit_code == 0

    def test_migrate_propagates_exit_code(self):
        runner = CliRunner()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = runner.invoke(cli, ["migrate"])
        assert result.exit_code == 1

    def test_migrate_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["migrate", "--help"])
        assert result.exit_code == 0
        assert "alembic" in result.output.lower() or "migration" in result.output.lower()


class TestWorkerCommand:
    def test_worker_default_kinds(self):
        runner = CliRunner()
        mock_loop = MagicMock()
        mock_loop.run_until_stopped = AsyncMock(return_value=None)

        with patch("src.modules.platform.worker.WorkerLoop", return_value=mock_loop) as mock_cls:
            result = runner.invoke(cli, ["worker"])

        mock_cls.assert_called_once_with(kinds=["send_login_email", "spend_alert"])
        assert result.exit_code == 0

    def test_worker_custom_kinds(self):
        runner = CliRunner()
        mock_loop = MagicMock()
        mock_loop.run_until_stopped = AsyncMock(return_value=None)

        with patch("src.modules.platform.worker.WorkerLoop", return_value=mock_loop) as mock_cls:
            result = runner.invoke(cli, ["worker", "--kinds", "registry.sync,send_login_email"])

        mock_cls.assert_called_once_with(kinds=["registry.sync", "send_login_email"])
        assert result.exit_code == 0

    def test_worker_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["worker", "--help"])
        assert result.exit_code == 0
        assert "--kinds" in result.output


class TestServeCommand:
    def test_serve_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output
        assert "--reload" in result.output

    def test_serve_calls_uvicorn(self):
        runner = CliRunner()
        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(cli, ["serve", "--host", "127.0.0.1", "--port", "9000"])
        mock_run.assert_called_once_with(
            "src.modules.api.app:app",
            host="127.0.0.1",
            port=9000,
            reload=False,
        )
        assert result.exit_code == 0

    def test_serve_reload_flag(self):
        runner = CliRunner()
        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(cli, ["serve", "--reload"])
        assert mock_run.call_args.kwargs["reload"] is True
        assert result.exit_code == 0


class TestSyncNowCommand:
    def test_sync_now_enqueues_job(self):
        runner = CliRunner()
        import uuid

        fake_id = uuid.uuid4()

        async def _fake_enqueue(*args, **kwargs):
            return fake_id

        mock_conn = AsyncMock()

        class _FakeTransaction:
            async def __aenter__(self):
                return mock_conn

            async def __aexit__(self, *args):
                pass

        with (
            patch("src.modules.platform.db.transaction", return_value=_FakeTransaction()),
            patch("src.modules.platform.jobs.enqueue", side_effect=_fake_enqueue),
        ):
            result = runner.invoke(cli, ["sync-now"])

        assert result.exit_code == 0
        assert "registry.sync" in result.output
