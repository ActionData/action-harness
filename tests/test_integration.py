"""Integration tests for the full pipeline. Uses a real git repo with mocked Claude CLI."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from action_harness.models import EvalResult
from action_harness.pipeline import run_pipeline


@pytest.fixture
def test_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with pyproject.toml, a test, and an OpenSpec change."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    # Create pyproject.toml
    (repo / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"\n')

    # Create a passing test
    (repo / "tests").mkdir()
    (repo / "tests" / "__init__.py").write_text("")
    (repo / "tests" / "test_basic.py").write_text("def test_ok() -> None:\n    assert True\n")

    # Create an OpenSpec change directory
    change_dir = repo / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [ ] 1.1 Add a feature\n")

    # Create src directory
    (repo / "src").mkdir()

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    return repo


def _make_claude_mock(
    commits: bool = True,
    returncode: int = 0,
    cost: float = 0.10,
) -> MagicMock:
    """Create a mock for subprocess.run that simulates the claude CLI.

    When commits=True, the mock creates a file and commits it in the worktree
    before returning (simulating a worker that produces work).
    """
    original_run = subprocess.run

    def side_effect(
        cmd: list[str], **kwargs: object
    ) -> MagicMock | subprocess.CompletedProcess[str]:
        if cmd[0] == "claude":
            # Simulate the worker producing a commit
            cwd = kwargs.get("cwd")
            if commits and cwd:
                cwd_path = Path(str(cwd))
                (cwd_path / "new_feature.py").write_text("# new feature\n")
                original_run(["git", "add", "."], cwd=cwd_path, capture_output=True)
                original_run(
                    ["git", "commit", "-m", "Add feature"],
                    cwd=cwd_path,
                    capture_output=True,
                )
            result = MagicMock()
            result.returncode = returncode
            result.stdout = json.dumps({"cost_usd": cost, "result": "implemented"})
            result.stderr = ""
            return result
        elif cmd[0] == "gh":
            result = MagicMock()
            result.returncode = 0
            result.stdout = "https://github.com/test/repo/pull/1"
            result.stderr = ""
            return result
        elif cmd[0] == "git" and "push" in cmd:
            # Simulate successful push
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result
        else:
            # Pass through to real git for worktree operations, rev-list, etc.
            return original_run(cmd, **kwargs)

    mock = MagicMock(side_effect=side_effect)
    return mock


class TestPipelineSuccess:
    def _passing_eval(self) -> EvalResult:
        return EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4)

    def test_full_pipeline_happy_path(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=True)

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=self._passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
        ):
            result = run_pipeline("test-change", test_repo, max_retries=1)

        assert result.success is True
        assert result.pr_url == "https://github.com/test/repo/pull/1"
        assert result.branch == "harness/test-change"

    def test_pipeline_creates_worktree(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=True)

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=self._passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
        ):
            run_pipeline("test-change", test_repo)

        # Verify branch was created
        check = subprocess.run(
            ["git", "rev-parse", "--verify", "harness/test-change"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )
        assert check.returncode == 0

    def test_worker_invoked_with_correct_args(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=True)

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=self._passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
        ):
            run_pipeline("test-change", test_repo, max_turns=50)

        # Find claude invocation
        claude_calls = [c for c in mock.call_args_list if c[0][0][0] == "claude"]
        assert len(claude_calls) >= 1
        cmd = claude_calls[0][0][0]
        assert "--system-prompt" in cmd
        assert "--max-turns" in cmd
        idx = cmd.index("--max-turns")
        assert cmd[idx + 1] == "50"


class TestPipelineFailure:
    def test_worker_no_commits_retries_then_fails(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=False)

        with patch("action_harness.worker.subprocess.run", mock):
            result = run_pipeline("test-change", test_repo, max_retries=2)

        assert result.success is False
        assert "Worker failed" in (result.error or "") or "No commits" in (result.error or "")

    def test_max_retries_respected(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=False)

        with patch("action_harness.worker.subprocess.run", mock):
            run_pipeline("test-change", test_repo, max_retries=2)

        # Count claude invocations — should be max_retries + 1 (initial + retries)
        claude_calls = [c for c in mock.call_args_list if c[0][0][0] == "claude"]
        assert len(claude_calls) == 3  # 1 initial + 2 retries

    def test_worktree_failure_returns_error(self, tmp_path: Path) -> None:
        """Pipeline fails gracefully when worktree creation fails."""
        # tmp_path has git init but no commits — worktree add will fail
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        change_dir = tmp_path / "openspec" / "changes" / "test-change"
        change_dir.mkdir(parents=True)

        result = run_pipeline("test-change", tmp_path)

        assert result.success is False
        assert result.error is not None

    def test_worktree_cleaned_up_on_failure(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=False)

        with patch("action_harness.worker.subprocess.run", mock):
            result = run_pipeline("test-change", test_repo, max_retries=0)

        assert result.success is False

        # Worktree should be cleaned up (no lingering worktrees)
        list_result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )
        worktrees = [
            line
            for line in list_result.stdout.splitlines()
            if line.startswith("worktree ") and "harness" in line
        ]
        assert len(worktrees) == 0
