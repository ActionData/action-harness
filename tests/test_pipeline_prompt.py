"""Tests for pipeline behavior in prompt mode (no OpenSpec change)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from action_harness.models import (
    OpenSpecReviewResult,
)
from action_harness.pipeline import run_pipeline


def _make_subprocess_mock(
    eval_pass: bool = True,
) -> MagicMock:
    """Create a subprocess mock that handles all pipeline stages.

    When eval_pass is False, eval commands fail on the first call and succeed
    on subsequent calls (to simulate a retry-then-pass scenario).
    """
    mock = MagicMock()
    eval_call_count = {"n": 0}

    def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""

        if cmd[0] == "claude":
            result.stdout = json.dumps({"cost_usd": 0.01, "result": "ok"})
        elif cmd[0] == "git" and "rev-list" in cmd:
            result.stdout = "1\n"
        elif cmd[0] == "git" and "symbolic-ref" in cmd:
            result.stdout = "refs/remotes/origin/main\n"
        elif cmd[0] == "git" and "worktree" in cmd and "add" in cmd:
            result.stdout = ""
        elif cmd[0] == "git" and "push" in cmd:
            result.stdout = ""
        elif cmd[0] == "git" and "diff" in cmd:
            result.stdout = "file.py | 5 +++++\n"
        elif cmd[0] == "git" and "log" in cmd:
            result.stdout = "abc1234 Fix bug\n"
        elif cmd[0] == "gh" and "pr" in cmd and "create" in cmd:
            result.stdout = "https://github.com/test/repo/pull/1\n"
        elif cmd[0] == "gh" and "pr" in cmd and "comment" in cmd:
            result.stdout = ""
        else:
            # Eval commands (uv run pytest, ruff, etc.)
            if not eval_pass:
                eval_call_count["n"] += 1
                # First batch of eval commands (4 commands) fails on the 1st
                if eval_call_count["n"] == 1:
                    result.returncode = 1
                    result.stdout = "FAIL"
                    result.stderr = "test failed"
            result.stdout = result.stdout or ""
        return result

    mock.side_effect = side_effect
    return mock


def _setup_fake_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repo for pipeline tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


def _get_claude_calls(mock: MagicMock) -> list[list[str]]:
    """Extract all claude CLI calls from mock."""
    return [call[0][0] for call in mock.call_args_list if call[0][0][0] == "claude"]


def _get_claude_user_prompt(cmd: list[str]) -> str:
    """Extract the -p value from a claude CLI command."""
    idx = cmd.index("-p")
    return cmd[idx + 1]


def _get_claude_system_prompt(cmd: list[str]) -> str | None:
    """Extract the --system-prompt value from a claude CLI command, or None."""
    if "--system-prompt" not in cmd:
        return None
    idx = cmd.index("--system-prompt")
    return cmd[idx + 1]


@pytest.fixture(autouse=True)
def _mock_preflight(mock_preflight: None) -> None:
    """Auto-apply shared mock_preflight fixture from conftest."""


class TestPipelinePromptMode:
    """Tests for pipeline behavior with prompt parameter."""

    def test_no_openspec_review_in_prompt_mode(self, tmp_path: Path) -> None:
        """When pipeline runs with prompt, no OpenSpecReviewResult should appear."""
        repo = _setup_fake_repo(tmp_path)
        mock = _make_subprocess_mock()

        with (
            patch("action_harness.pipeline.subprocess.run", mock),
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.evaluator.subprocess.run", mock),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.worktree.subprocess.run", mock),
            patch("action_harness.protection.load_protected_patterns", return_value=[]),
        ):
            pr_result, manifest = run_pipeline(
                change_name="prompt-fix-bug",
                repo=repo,
                max_retries=0,
                max_turns=10,
                skip_review=True,
                prompt="Fix the bug",
            )

        # No OpenSpecReviewResult in stages
        openspec_stages = [s for s in manifest.stages if isinstance(s, OpenSpecReviewResult)]
        assert len(openspec_stages) == 0

    def test_openspec_review_runs_without_prompt(self, tmp_path: Path) -> None:
        """When pipeline runs without prompt (change mode), OpenSpec review runs."""
        repo = _setup_fake_repo(tmp_path)
        # Create change dir for OpenSpec review
        change_dir = repo / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        mock = _make_subprocess_mock()

        with (
            patch("action_harness.pipeline.subprocess.run", mock),
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.evaluator.subprocess.run", mock),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.worktree.subprocess.run", mock),
            patch("action_harness.openspec_reviewer.subprocess.run", mock),
            patch("action_harness.protection.load_protected_patterns", return_value=[]),
        ):
            pr_result, manifest = run_pipeline(
                change_name="my-change",
                repo=repo,
                max_retries=0,
                max_turns=10,
                skip_review=True,
            )

        # Should have an OpenSpecReviewResult in stages
        openspec_stages = [s for s in manifest.stages if isinstance(s, OpenSpecReviewResult)]
        assert len(openspec_stages) > 0

    def test_prompt_forwarded_to_worker(self, tmp_path: Path) -> None:
        """Verify the prompt string reaches the claude CLI as the user prompt."""
        repo = _setup_fake_repo(tmp_path)
        worker_mock = _make_subprocess_mock()

        with (
            patch("action_harness.pipeline.subprocess.run", worker_mock),
            patch("action_harness.worker.subprocess.run", worker_mock),
            patch("action_harness.evaluator.subprocess.run", worker_mock),
            patch("action_harness.pr.subprocess.run", worker_mock),
            patch("action_harness.worktree.subprocess.run", worker_mock),
            patch("action_harness.protection.load_protected_patterns", return_value=[]),
        ):
            run_pipeline(
                change_name="prompt-fix-bug",
                repo=repo,
                max_retries=0,
                max_turns=10,
                skip_review=True,
                prompt="Fix the bug",
            )

        claude_calls = _get_claude_calls(worker_mock)
        assert len(claude_calls) >= 1
        # First claude call should be the worker dispatch
        user_prompt = _get_claude_user_prompt(claude_calls[0])
        assert "Fix the bug" in user_prompt
        # System prompt should be generic, not opsx-apply
        sys_prompt = _get_claude_system_prompt(claude_calls[0])
        assert sys_prompt is not None
        assert "opsx-apply" not in sys_prompt
        assert "implementing a task" in sys_prompt

    def test_prompt_forwarded_on_retry(self, tmp_path: Path) -> None:
        """When eval fails and retries, the prompt is still forwarded to the worker."""
        repo = _setup_fake_repo(tmp_path)
        mock = _make_subprocess_mock()

        from action_harness.models import EvalResult

        eval_results = iter(
            [
                # First eval after worker 1: fails
                EvalResult(
                    success=False,
                    stage="eval",
                    error="test failed",
                    commands_run=1,
                    commands_passed=0,
                    failed_command="uv run pytest",
                    feedback_prompt="## Eval Failure\nuv run pytest failed",
                ),
                # Pre-work eval before retry: also fails (so retry dispatches worker 2)
                EvalResult(
                    success=False,
                    stage="eval",
                    error="test still failed",
                    commands_run=1,
                    commands_passed=0,
                    failed_command="uv run pytest",
                    feedback_prompt="## Eval Failure\nstill failing",
                ),
                # Eval after worker 2: passes
                EvalResult(
                    success=True,
                    stage="eval",
                    commands_run=1,
                    commands_passed=1,
                ),
            ]
        )

        with (
            patch("action_harness.pipeline.subprocess.run", mock),
            patch("action_harness.worker.subprocess.run", mock),
            patch(
                "action_harness.pipeline.run_eval",
                side_effect=lambda *a, **kw: next(eval_results),
            ),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.worktree.subprocess.run", mock),
            patch("action_harness.protection.load_protected_patterns", return_value=[]),
        ):
            run_pipeline(
                change_name="prompt-fix-bug",
                repo=repo,
                max_retries=1,
                max_turns=10,
                skip_review=True,
                prompt="Fix the bug",
            )

        claude_calls = _get_claude_calls(mock)
        # Should have at least 2 worker dispatches (initial + retry)
        assert len(claude_calls) >= 2
        # Both should contain the prompt in their user prompt
        for cmd in claude_calls:
            user_prompt = _get_claude_user_prompt(cmd)
            assert "Fix the bug" in user_prompt
