"""Tests for CLI entrypoint and input validation."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from action_harness.cli import ValidationError, app, validate_inputs
from action_harness.models import PrResult, RunManifest

runner = CliRunner()


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Create a minimal fake git repo with an OpenSpec change directory."""
    (tmp_path / ".git").mkdir()
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    return tmp_path


def test_valid_inputs(fake_repo: Path) -> None:
    with patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock") as mock_which:
        validate_inputs("test-change", fake_repo)
    mock_which.assert_any_call("claude")
    mock_which.assert_any_call("gh")


def test_missing_repo() -> None:
    with pytest.raises(ValidationError, match="Repository path does not exist"):
        validate_inputs("anything", Path("/nonexistent/repo/path"))


def test_not_a_git_repo(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="Not a git repository"):
        validate_inputs("anything", tmp_path)


def test_missing_change_dir(fake_repo: Path) -> None:
    with pytest.raises(ValidationError, match="Change directory not found"):
        validate_inputs("nonexistent-change", fake_repo)


def test_path_traversal_in_change_name(fake_repo: Path) -> None:
    with pytest.raises(ValidationError, match="path traversal"):
        validate_inputs("../../..", fake_repo)


def test_missing_claude_cli(fake_repo: Path) -> None:
    def selective_which(cmd: str) -> str | None:
        if cmd == "claude":
            return None
        return "/usr/bin/mock"

    with patch("action_harness.cli.shutil.which", side_effect=selective_which):
        with pytest.raises(ValidationError, match="claude CLI not found"):
            validate_inputs("test-change", fake_repo)


def test_missing_gh_cli(fake_repo: Path) -> None:
    def selective_which(cmd: str) -> str | None:
        if cmd == "gh":
            return None
        return "/usr/bin/mock"

    with patch("action_harness.cli.shutil.which", side_effect=selective_which):
        with pytest.raises(ValidationError, match="gh CLI not found"):
            validate_inputs("test-change", fake_repo)


class TestCliRunner:
    """Test the typer CLI command via CliRunner."""

    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_top_level_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.output

    def test_run_subcommand_required(self) -> None:
        result = runner.invoke(app, ["--change", "x", "--repo", "/some/path"])
        assert result.exit_code != 0

    def _mock_pipeline_success(self) -> tuple[PrResult, RunManifest]:
        pr_result = PrResult(
            success=True,
            stage="pipeline",
            pr_url="https://github.com/test/repo/pull/1",
            branch="harness/test",
        )
        manifest = RunManifest(
            change_name="test-change",
            repo_path="/tmp/repo",
            started_at="2026-01-01T00:00:00+00:00",
            completed_at="2026-01-01T00:01:00+00:00",
            success=True,
            stages=[],
            total_duration_seconds=60.0,
            pr_url="https://github.com/test/repo/pull/1",
            manifest_path="/tmp/repo/.action-harness/runs/test.json",
        )
        return pr_result, manifest

    def test_run_valid_inputs(self, fake_repo: Path) -> None:
        with (
            patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"),
            patch(
                "action_harness.pipeline.run_pipeline", return_value=self._mock_pipeline_success()
            ),
        ):
            result = runner.invoke(
                app, ["run", "--change", "test-change", "--repo", str(fake_repo)]
            )
        assert result.exit_code == 0

    def test_run_missing_repo(self) -> None:
        result = runner.invoke(app, ["run", "--change", "x", "--repo", "/nonexistent/path"])
        assert result.exit_code == 1

    def test_help_shows_all_flags(self) -> None:
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--verbose" in result.output
        assert "--dry-run" in result.output
        assert "--model" in result.output
        assert "--effort" in result.output
        assert "--max-budget-usd" in result.output
        assert "--permission-mode" in result.output

    def test_verbose_flag_accepted(self, fake_repo: Path) -> None:
        with (
            patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"),
            patch(
                "action_harness.pipeline.run_pipeline", return_value=self._mock_pipeline_success()
            ),
        ):
            result = runner.invoke(
                app,
                ["run", "--change", "test-change", "--repo", str(fake_repo), "--verbose"],
            )
        assert result.exit_code == 0

    def test_dry_run_prints_full_plan(self, fake_repo: Path) -> None:
        with patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"):
            result = runner.invoke(
                app,
                ["run", "--change", "test-change", "--repo", str(fake_repo), "--dry-run"],
            )
        assert result.exit_code == 0
        assert "test-change" in result.output
        assert "harness/test-change" in result.output
        assert "uv run pytest -v" in result.output
        assert "uv run ruff check" in result.output
        assert "uv run ruff format" in result.output
        assert "uv run mypy src/" in result.output
        assert "claude --output-format json" in result.output
        assert "[harness] test-change" in result.output
        assert "max retries: 3" in result.output
        # Worker config defaults
        assert "model: default" in result.output
        assert "effort: default" in result.output
        assert "max-budget-usd: none" in result.output
        assert "permission-mode: bypassPermissions" in result.output

    def test_dry_run_reflects_custom_options(self, fake_repo: Path) -> None:
        with patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"):
            result = runner.invoke(
                app,
                [
                    "run",
                    "--change",
                    "test-change",
                    "--repo",
                    str(fake_repo),
                    "--dry-run",
                    "--max-retries",
                    "7",
                    "--max-turns",
                    "50",
                ],
            )
        assert result.exit_code == 0
        assert "max retries: 7" in result.output
        assert "--max-turns 50" in result.output

    def test_dry_run_shows_worker_config(self, fake_repo: Path) -> None:
        with patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"):
            result = runner.invoke(
                app,
                [
                    "run",
                    "--change",
                    "test-change",
                    "--repo",
                    str(fake_repo),
                    "--dry-run",
                    "--model",
                    "sonnet",
                    "--effort",
                    "high",
                    "--max-budget-usd",
                    "2.0",
                    "--permission-mode",
                    "plan",
                ],
            )
        assert result.exit_code == 0
        assert "model: sonnet" in result.output
        assert "effort: high" in result.output
        assert "max-budget-usd: 2.0" in result.output
        assert "permission-mode: plan" in result.output

    def test_dry_run_invalid_inputs(self) -> None:
        result = runner.invoke(
            app,
            ["run", "--change", "nonexistent", "--repo", "/nonexistent", "--dry-run"],
        )
        assert result.exit_code == 1
