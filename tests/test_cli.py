"""Tests for CLI entrypoint and input validation."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from action_harness.cli import ValidationError, app, validate_inputs, validate_inputs_prompt
from action_harness.models import PrResult, RunManifest

runner = CliRunner()


def _mock_pipeline_success(
    change_name: str = "test-change",
) -> tuple[PrResult, RunManifest]:
    """Shared helper: a successful pipeline result for CLI tests."""
    pr_result = PrResult(
        success=True,
        stage="pipeline",
        pr_url="https://github.com/test/repo/pull/1",
        branch="harness/test",
    )
    manifest = RunManifest(
        change_name=change_name,
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

    def test_run_valid_inputs(self, fake_repo: Path) -> None:
        with (
            patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"),
            patch("action_harness.pipeline.run_pipeline", return_value=_mock_pipeline_success()),
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
            patch("action_harness.pipeline.run_pipeline", return_value=_mock_pipeline_success()),
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
        # Profiler output: ecosystem and source should be displayed
        assert "ecosystem:" in result.output
        assert "profile source:" in result.output
        assert "eval commands:" in result.output
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

    def test_help_shows_harness_home(self) -> None:
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--harness-home" in result.output

    def test_help_shows_clean_subcommand(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "clean" in result.output

    def test_repo_help_mentions_urls(self) -> None:
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "owner/repo" in result.output

    def test_help_shows_auto_merge_and_wait_for_ci(self) -> None:
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--auto-merge" in result.output
        assert "--wait-for-ci" in result.output

    def test_dry_run_with_auto_merge(self, fake_repo: Path) -> None:
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
                    "--auto-merge",
                ],
            )
        assert result.exit_code == 0
        assert "auto-merge: enabled" in result.output
        assert "wait-for-ci: disabled" in result.output

    def test_dry_run_without_auto_merge(self, fake_repo: Path) -> None:
        with patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"):
            result = runner.invoke(
                app,
                ["run", "--change", "test-change", "--repo", str(fake_repo), "--dry-run"],
            )
        assert result.exit_code == 0
        assert "auto-merge: disabled" in result.output

    def test_wait_for_ci_without_auto_merge_errors(self) -> None:
        result = runner.invoke(
            app,
            ["run", "--change", "x", "--repo", "/nonexistent", "--wait-for-ci"],
        )
        assert result.exit_code == 1
        assert "--wait-for-ci requires --auto-merge" in result.output


class TestValidateInputsPrompt:
    """Tests for validate_inputs_prompt (prompt mode)."""

    def test_valid_prompt_inputs(self, fake_repo: Path) -> None:
        with patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"):
            validate_inputs_prompt(fake_repo)

    def test_missing_repo_prompt_mode(self) -> None:
        with pytest.raises(ValidationError, match="Repository path does not exist"):
            validate_inputs_prompt(Path("/nonexistent/repo"))

    def test_not_git_repo_prompt_mode(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="Not a git repository"):
            validate_inputs_prompt(tmp_path)

    def test_does_not_check_openspec_dir(self, tmp_path: Path) -> None:
        """Prompt mode should NOT check for openspec directory."""
        (tmp_path / ".git").mkdir()
        # No openspec dir — should still pass
        with patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"):
            validate_inputs_prompt(tmp_path)

    def test_missing_claude_cli_prompt_mode(self, fake_repo: Path) -> None:
        def selective_which(cmd: str) -> str | None:
            return None if cmd == "claude" else "/usr/bin/mock"

        with patch("action_harness.cli.shutil.which", side_effect=selective_which):
            with pytest.raises(ValidationError, match="claude CLI not found"):
                validate_inputs_prompt(fake_repo)

    def test_missing_gh_cli_prompt_mode(self, fake_repo: Path) -> None:
        def selective_which(cmd: str) -> str | None:
            return None if cmd == "gh" else "/usr/bin/mock"

        with patch("action_harness.cli.shutil.which", side_effect=selective_which):
            with pytest.raises(ValidationError, match="gh CLI not found"):
                validate_inputs_prompt(fake_repo)


class TestPromptModeCli:
    """Test --prompt flag behavior in the CLI."""

    def test_both_change_and_prompt_fails(self) -> None:
        result = runner.invoke(
            app,
            ["run", "--change", "x", "--prompt", "Fix bug", "--repo", "/some/path"],
        )
        assert result.exit_code == 1
        assert "Specify either --change or --prompt, not both" in result.output

    def test_neither_change_nor_prompt_fails(self) -> None:
        result = runner.invoke(app, ["run", "--repo", "/some/path"])
        assert result.exit_code == 1
        assert "Specify either --change or --prompt" in result.output

    def test_prompt_only_works(self, fake_repo: Path) -> None:
        with (
            patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"),
            patch(
                "action_harness.pipeline.run_pipeline",
                return_value=_mock_pipeline_success(),
            ),
        ):
            result = runner.invoke(
                app,
                ["run", "--prompt", "Fix bug in auth", "--repo", str(fake_repo)],
            )
        assert result.exit_code == 0

    def test_change_only_still_works(self, fake_repo: Path) -> None:
        with (
            patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"),
            patch(
                "action_harness.pipeline.run_pipeline",
                return_value=_mock_pipeline_success(),
            ),
        ):
            result = runner.invoke(
                app,
                ["run", "--change", "test-change", "--repo", str(fake_repo)],
            )
        assert result.exit_code == 0

    def test_dry_run_with_prompt(self, fake_repo: Path) -> None:
        with patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"):
            result = runner.invoke(
                app,
                [
                    "run",
                    "--prompt",
                    "Add a hello world test",
                    "--repo",
                    str(fake_repo),
                    "--dry-run",
                ],
            )
        assert result.exit_code == 0
        assert "Add a hello world test" in result.output
        assert "harness/prompt-add-a-hello-world-test" in result.output

    def test_help_shows_prompt_flag(self) -> None:
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--prompt" in result.output

    def test_empty_prompt_fails(self) -> None:
        result = runner.invoke(app, ["run", "--prompt", "", "--repo", "/some/path"])
        assert result.exit_code == 1
        assert "--prompt must not be empty" in result.output

    def test_whitespace_only_prompt_fails(self) -> None:
        result = runner.invoke(app, ["run", "--prompt", "   ", "--repo", "/some/path"])
        assert result.exit_code == 1
        assert "--prompt must not be empty" in result.output

    def test_special_chars_only_prompt_fails(self, fake_repo: Path) -> None:
        """A prompt like '!!@@##' passes strip() but yields empty slug."""
        with patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"):
            result = runner.invoke(
                app,
                ["run", "--prompt", "!!@@##$$", "--repo", str(fake_repo)],
            )
        assert result.exit_code == 1
        assert "alphanumeric" in result.output


class TestCleanCommand:
    """Test the clean subcommand."""

    def test_clean_requires_repo_or_all(self) -> None:
        result = runner.invoke(app, ["clean"])
        assert result.exit_code == 1
        assert "specify --repo or --all" in result.output

    def test_clean_no_workspaces_dir(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["clean", "--all", "--harness-home", str(tmp_path)])
        assert result.exit_code == 0
        assert "no workspaces directory" in result.output

    def test_clean_specific_workspace(self, tmp_path: Path) -> None:
        """Clean a specific workspace directory."""
        harness_home = tmp_path / "harness"
        ws_dir = harness_home / "workspaces" / "my-app" / "fix-bug"
        ws_dir.mkdir(parents=True)

        # Create a fake repo clone for resolve_repo to find
        repo_dir = harness_home / "repos" / "my-app"
        repo_dir.mkdir(parents=True)
        # Init a git repo so git commands don't fail hard
        subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )

        result = runner.invoke(
            app,
            [
                "clean",
                "--repo",
                str(repo_dir),
                "--change",
                "fix-bug",
                "--harness-home",
                str(harness_home),
            ],
        )
        assert result.exit_code == 0
        assert not ws_dir.exists()

    def test_clean_all_for_repo(self, tmp_path: Path) -> None:
        """Clean all workspaces for a repo."""
        harness_home = tmp_path / "harness"
        ws_base = harness_home / "workspaces" / "my-app"
        (ws_base / "fix-a").mkdir(parents=True)
        (ws_base / "fix-b").mkdir(parents=True)

        # Create repo clone
        repo_dir = harness_home / "repos" / "my-app"
        repo_dir.mkdir(parents=True)
        subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )

        result = runner.invoke(
            app,
            [
                "clean",
                "--repo",
                str(repo_dir),
                "--harness-home",
                str(harness_home),
            ],
        )
        assert result.exit_code == 0
        assert not (ws_base / "fix-a").exists()
        assert not (ws_base / "fix-b").exists()

    def test_clean_all(self, tmp_path: Path) -> None:
        """Clean all workspaces across all repos."""
        harness_home = tmp_path / "harness"
        (harness_home / "workspaces" / "app1" / "change1").mkdir(parents=True)
        (harness_home / "workspaces" / "app2" / "change2").mkdir(parents=True)

        result = runner.invoke(app, ["clean", "--all", "--harness-home", str(harness_home)])
        assert result.exit_code == 0
        assert "all workspaces removed" in result.output
        # Workspace dirs should be cleaned up
        assert not (harness_home / "workspaces" / "app1" / "change1").exists()
        assert not (harness_home / "workspaces" / "app2" / "change2").exists()
