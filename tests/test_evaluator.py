"""Tests for subprocess eval runner."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from action_harness.evaluator import (
    BOOTSTRAP_EVAL_COMMANDS,
    format_feedback,
    run_eval,
)
from action_harness.models import EvalResult


class TestBootstrapEvalCommands:
    def test_contains_expected_commands(self) -> None:
        assert "uv run pytest -v" in BOOTSTRAP_EVAL_COMMANDS
        assert "uv run ruff check ." in BOOTSTRAP_EVAL_COMMANDS
        assert "uv run ruff format --check ." in BOOTSTRAP_EVAL_COMMANDS
        assert "uv run mypy src/" in BOOTSTRAP_EVAL_COMMANDS

    def test_has_four_commands(self) -> None:
        assert len(BOOTSTRAP_EVAL_COMMANDS) == 4


class TestFormatFeedback:
    def test_includes_command(self) -> None:
        feedback = format_feedback("uv run pytest -v", 1, "FAILED test_foo")
        assert "uv run pytest -v" in feedback

    def test_includes_exit_code(self) -> None:
        feedback = format_feedback("uv run pytest -v", 2, "error output")
        assert "### Exit Code: 2" in feedback

    def test_includes_output(self) -> None:
        feedback = format_feedback("uv run pytest -v", 1, "FAILED test_foo\nassert False")
        assert "FAILED test_foo" in feedback
        assert "assert False" in feedback

    def test_includes_fix_instruction(self) -> None:
        feedback = format_feedback("cmd", 1, "err")
        assert "Fix these issues" in feedback

    def test_markdown_structure(self) -> None:
        feedback = format_feedback("cmd", 1, "output")
        assert feedback.startswith("## Eval Failure")
        assert "### Command:" in feedback
        assert "### Exit Code:" in feedback
        assert "### Output:" in feedback
        assert "```" in feedback


class TestRunEval:
    def _make_mock(self, results: list[tuple[int, str, str]]) -> MagicMock:
        """Create mock for subprocess.run with a sequence of (returncode, stdout, stderr)."""
        mock = MagicMock()
        returns = []
        for rc, stdout, stderr in results:
            r = MagicMock()
            r.returncode = rc
            r.stdout = stdout
            r.stderr = stderr
            returns.append(r)
        mock.side_effect = returns
        return mock

    def test_all_pass(self) -> None:
        results = [(0, "ok", "") for _ in range(4)]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            result = run_eval(Path("/fake/worktree"))

        assert result.success is True
        assert result.commands_run == 4
        assert result.commands_passed == 4
        assert result.failed_command is None
        assert result.feedback_prompt is None
        assert result.error is None
        assert isinstance(result, EvalResult)

    def test_first_command_fails(self) -> None:
        results = [(1, "", "pytest: error")]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            result = run_eval(Path("/fake/worktree"))

        assert result.success is False
        assert result.commands_run == 1
        assert result.commands_passed == 0
        assert result.failed_command == "uv run pytest -v"
        assert result.feedback_prompt is not None
        assert "uv run pytest -v" in result.feedback_prompt

    def test_second_command_fails(self) -> None:
        results = [
            (0, "ok", ""),  # pytest passes
            (1, "ruff error", ""),  # ruff fails
        ]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            result = run_eval(Path("/fake/worktree"))

        assert result.success is False
        assert result.commands_run == 2
        assert result.commands_passed == 1
        assert result.failed_command == "uv run ruff check ."

    def test_stops_on_first_failure(self) -> None:
        results = [
            (0, "ok", ""),
            (1, "fail", ""),
        ]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            run_eval(Path("/fake/worktree"))

        # Should only have called subprocess.run twice (not 4 times)
        assert mock.call_count == 2

    def test_custom_eval_commands(self) -> None:
        custom = ["make test", "make lint"]
        results = [(0, "ok", "") for _ in range(2)]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            result = run_eval(Path("/fake/worktree"), eval_commands=custom)

        assert result.success is True
        assert result.commands_run == 2
        assert result.commands_passed == 2

    def test_runs_in_worktree_directory(self) -> None:
        results = [(0, "ok", "") for _ in range(4)]
        mock = self._make_mock(results)
        wt = Path("/my/worktree")

        with patch("action_harness.evaluator.subprocess.run", mock):
            run_eval(wt)

        for c in mock.call_args_list:
            assert c[1]["cwd"] == wt

    def test_command_not_found_returns_failure(self) -> None:
        mock = MagicMock(side_effect=FileNotFoundError("No such file: nonexistent"))

        with patch("action_harness.evaluator.subprocess.run", mock):
            result = run_eval(Path("/fake/worktree"), eval_commands=["nonexistent --flag"])

        assert result.success is False
        assert "Failed to execute" in (result.error or "")
        assert result.failed_command == "nonexistent --flag"

    def test_feedback_includes_combined_output(self) -> None:
        results = [(1, "stdout content", "stderr content")]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            result = run_eval(Path("/fake/worktree"))

        assert result.feedback_prompt is not None
        assert "stdout content" in result.feedback_prompt
        assert "stderr content" in result.feedback_prompt
