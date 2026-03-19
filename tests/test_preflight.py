"""Tests for pre-dispatch preflight checks."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from action_harness.models import PreflightResult, WorkerResult
from action_harness.preflight import (
    check_eval_tools,
    check_git_remote,
    check_prerequisites,
    check_worktree_clean,
    run_preflight,
)

# --- check_worktree_clean ---


def test_worktree_clean_returns_true_on_clean(tmp_path: Path) -> None:
    """Clean worktree passes the check."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    (tmp_path / "f.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    result = check_worktree_clean(tmp_path)
    assert result is True


def test_worktree_clean_returns_false_on_dirty(tmp_path: Path) -> None:
    """Dirty worktree fails the check."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    (tmp_path / "f.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    # Create uncommitted change
    (tmp_path / "dirty.txt").write_text("dirty")
    result = check_worktree_clean(tmp_path)
    assert result is False


def test_worktree_clean_handles_subprocess_error() -> None:
    """Returns False when git status fails."""
    with patch("action_harness.preflight.subprocess.run", side_effect=OSError("no git")):
        result = check_worktree_clean(Path("/nonexistent"))
    assert result is False


# --- check_git_remote ---


def test_git_remote_returns_true_on_success(tmp_path: Path) -> None:
    """Reachable remote passes the check."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "abc123\tHEAD\n"
    mock_result.stderr = ""
    with patch("action_harness.preflight.subprocess.run", return_value=mock_result):
        result = check_git_remote(tmp_path)
    assert result is True


def test_git_remote_returns_false_on_unreachable(tmp_path: Path) -> None:
    """Unreachable remote fails the check."""
    mock_result = MagicMock()
    mock_result.returncode = 128
    mock_result.stdout = ""
    mock_result.stderr = "fatal: could not read from remote repository"
    with patch("action_harness.preflight.subprocess.run", return_value=mock_result):
        result = check_git_remote(tmp_path)
    assert result is False


def test_git_remote_returns_false_on_timeout(tmp_path: Path) -> None:
    """Timeout results in failure."""
    with patch(
        "action_harness.preflight.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30),
    ):
        result = check_git_remote(tmp_path)
    assert result is False


# --- check_eval_tools ---


def test_eval_tools_all_found() -> None:
    """All tools found in PATH passes."""
    with patch("action_harness.preflight.shutil.which", return_value="/usr/bin/tool"):
        ok, missing = check_eval_tools(["uv run pytest -v", "uv run ruff check ."])
    assert ok is True
    assert missing == []


def test_eval_tools_missing_tool() -> None:
    """Missing tool is reported."""

    def which_side_effect(name: str) -> str | None:
        if name == "uv":
            return "/usr/bin/uv"
        if name == "npm":
            return None
        return None

    with patch("action_harness.preflight.shutil.which", side_effect=which_side_effect):
        ok, missing = check_eval_tools(["uv run pytest -v", "npm test"])
    assert ok is False
    assert "npm" in missing


def test_eval_tools_deduplicates() -> None:
    """Same tool from multiple commands is only checked once."""
    call_count = 0

    def counting_which(name: str) -> str:
        nonlocal call_count
        call_count += 1
        return f"/usr/bin/{name}"

    with patch("action_harness.preflight.shutil.which", side_effect=counting_which):
        ok, missing = check_eval_tools(
            ["uv run pytest -v", "uv run ruff check .", "uv run mypy src/"]
        )
    assert ok is True
    assert call_count == 1  # "uv" checked only once


def test_eval_tools_empty_commands() -> None:
    """Empty command list passes."""
    ok, missing = check_eval_tools([])
    assert ok is True
    assert missing == []


# --- check_prerequisites ---


def test_prerequisites_returns_true_when_no_prereqs(tmp_path: Path) -> None:
    """No prerequisites means check passes."""
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    result = check_prerequisites("test-change", tmp_path)
    assert result is True


def test_prerequisites_returns_true_when_satisfied(tmp_path: Path) -> None:
    """All prerequisites satisfied passes."""
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)

    with (
        patch(
            "action_harness.preflight.read_prerequisites",
            return_value=["dep-a"],
        ),
        patch(
            "action_harness.preflight.is_prerequisite_satisfied",
            return_value=True,
        ),
    ):
        result = check_prerequisites("test-change", tmp_path)
    assert result is True


def test_prerequisites_returns_false_when_unmet(tmp_path: Path) -> None:
    """Unmet prerequisites fails."""
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)

    with (
        patch(
            "action_harness.preflight.read_prerequisites",
            return_value=["dep-a", "dep-b"],
        ),
        patch(
            "action_harness.preflight.is_prerequisite_satisfied",
            return_value=False,
        ),
    ):
        result = check_prerequisites("test-change", tmp_path)
    assert result is False


def test_prerequisites_returns_true_when_no_change_dir(tmp_path: Path) -> None:
    """Missing change dir is treated as no prerequisites."""
    result = check_prerequisites("nonexistent", tmp_path)
    assert result is True


# --- run_preflight ---


def test_run_preflight_all_pass(tmp_path: Path) -> None:
    """All checks passing returns success."""
    with (
        patch(
            "action_harness.preflight.check_worktree_clean",
            return_value=True,
        ),
        patch(
            "action_harness.preflight.check_git_remote",
            return_value=True,
        ),
        patch(
            "action_harness.preflight.check_eval_tools",
            return_value=(True, []),
        ),
        patch(
            "action_harness.preflight.check_prerequisites",
            return_value=True,
        ),
    ):
        result = run_preflight(
            worktree_path=tmp_path,
            eval_commands=["uv run pytest -v"],
            change_name="my-change",
            repo_path=tmp_path,
        )

    assert isinstance(result, PreflightResult)
    assert result.success is True
    assert result.failed_checks == []
    assert result.checks["worktree_clean"] is True
    assert result.checks["git_remote"] is True
    assert result.checks["eval_tools"] is True
    assert result.checks["prerequisites"] is True


def test_run_preflight_failure_reports_failed_checks(tmp_path: Path) -> None:
    """Failed checks are reported in the result."""
    with (
        patch(
            "action_harness.preflight.check_worktree_clean",
            return_value=True,
        ),
        patch(
            "action_harness.preflight.check_git_remote",
            return_value=False,
        ),
        patch(
            "action_harness.preflight.check_eval_tools",
            return_value=(False, ["npm"]),
        ),
        patch(
            "action_harness.preflight.check_prerequisites",
            return_value=True,
        ),
    ):
        result = run_preflight(
            worktree_path=tmp_path,
            eval_commands=["npm test"],
            change_name="my-change",
            repo_path=tmp_path,
        )

    assert result.success is False
    assert "git_remote" in result.failed_checks
    assert "eval_tools" in result.failed_checks
    assert "worktree_clean" not in result.failed_checks
    assert result.error is not None
    assert "git_remote" in result.error


def test_run_preflight_skips_prerequisites_in_prompt_mode(tmp_path: Path) -> None:
    """Prerequisites check is skipped when change_name is None (prompt mode)."""
    with (
        patch(
            "action_harness.preflight.check_worktree_clean",
            return_value=True,
        ),
        patch(
            "action_harness.preflight.check_git_remote",
            return_value=True,
        ),
        patch(
            "action_harness.preflight.check_eval_tools",
            return_value=(True, []),
        ),
        patch(
            "action_harness.preflight.check_prerequisites",
        ) as mock_prereqs,
    ):
        result = run_preflight(
            worktree_path=tmp_path,
            eval_commands=["uv run pytest -v"],
            change_name=None,
            repo_path=tmp_path,
        )

    assert result.success is True
    assert "prerequisites" not in result.checks
    mock_prereqs.assert_not_called()


# --- Pipeline integration ---


def test_preflight_failure_prevents_worker_dispatch(tmp_path: Path) -> None:
    """When preflight fails, worker dispatch should not be called."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    (repo / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"\n')

    change_dir = repo / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [ ] 1.1 Add feature\n")

    (repo / "src").mkdir()
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    failed_preflight = PreflightResult(
        success=False,
        stage="preflight",
        checks={"worktree_clean": True, "git_remote": False, "eval_tools": True},
        failed_checks=["git_remote"],
        error="Preflight failed: git_remote",
    )

    with (
        patch("action_harness.pipeline.run_preflight", return_value=failed_preflight),
        patch("action_harness.pipeline.dispatch_worker") as mock_worker,
        patch("action_harness.pipeline.cleanup_worktree"),
    ):
        from action_harness.pipeline import run_pipeline

        pr_result, manifest = run_pipeline(
            change_name="test-change",
            repo=repo,
        )

    assert pr_result.success is False
    assert "Preflight failed" in (pr_result.error or "")
    mock_worker.assert_not_called()


def test_skip_preflight_bypasses_checks(tmp_path: Path) -> None:
    """When skip_preflight=True, preflight is not run."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    (repo / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"\n')

    change_dir = repo / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [ ] 1.1 Add feature\n")

    (repo / "src").mkdir()
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    with (
        patch("action_harness.pipeline.run_preflight") as mock_preflight,
        patch("action_harness.pipeline.dispatch_worker") as mock_worker,
        patch("action_harness.pipeline.run_eval"),
        patch("action_harness.pipeline.create_pr"),
        patch("action_harness.pipeline.cleanup_worktree"),
    ):
        # Make worker fail so we don't have to mock the whole pipeline
        mock_worker.return_value = WorkerResult(
            success=False,
            stage="worker",
            error="mock failure",
            duration_seconds=1.0,
            commits_ahead=0,
        )

        from action_harness.pipeline import run_pipeline

        pr_result, _ = run_pipeline(
            change_name="test-change",
            repo=repo,
            max_retries=0,
            skip_preflight=True,
        )

    mock_preflight.assert_not_called()
