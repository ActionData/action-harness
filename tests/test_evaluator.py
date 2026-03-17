"""Tests for subprocess eval runner."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from action_harness.evaluator import (
    BOOTSTRAP_EVAL_COMMANDS,
    format_feedback,
    run_baseline_eval,
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

    def test_strips_virtual_env_from_subprocess_env(self) -> None:
        fake_environ: dict[str, str] = {
            "VIRTUAL_ENV": "/fake/path",
            "VIRTUAL_ENV_PROMPT": "fake",
            "PATH": "/usr/bin",
            "HOME": "/home/user",
        }
        results = [(0, "ok", "")]
        mock = self._make_mock(results)

        with (
            patch("action_harness.evaluator.os.environ", fake_environ),
            patch("action_harness.evaluator.subprocess.run", mock),
        ):
            run_eval(Path("/fake/worktree"), eval_commands=["echo hello"])

        assert mock.call_count == 1
        env: dict[str, str] = mock.call_args.kwargs["env"]
        assert "VIRTUAL_ENV" not in env
        assert "VIRTUAL_ENV_PROMPT" not in env
        assert env["PATH"] == "/usr/bin"
        assert env["HOME"] == "/home/user"

    def test_strips_venv_bin_from_path(self) -> None:
        fake_environ: dict[str, str] = {
            "VIRTUAL_ENV": "/fake/venv",
            "PATH": "/fake/venv/bin:/usr/local/bin:/usr/bin",
            "HOME": "/home/user",
        }
        results = [(0, "ok", "")]
        mock = self._make_mock(results)

        with (
            patch("action_harness.evaluator.os.environ", fake_environ),
            patch("action_harness.evaluator.subprocess.run", mock),
        ):
            run_eval(Path("/fake/worktree"), eval_commands=["echo hello"])

        env: dict[str, str] = mock.call_args.kwargs["env"]
        assert "/fake/venv/bin" not in env["PATH"].split(":")
        assert "/usr/local/bin" in env["PATH"].split(":")
        assert "/usr/bin" in env["PATH"].split(":")

    def test_env_passed_to_all_commands_in_multi_command_run(self) -> None:
        commands = ["echo one", "echo two", "echo three"]
        results = [(0, "ok", "") for _ in range(3)]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            result = run_eval(Path("/fake/worktree"), eval_commands=commands)

        assert result.success is True
        assert mock.call_count == 3
        for call in mock.call_args_list:
            assert "env" in call.kwargs, "env kwarg must be passed to every subprocess.run call"


class TestRunBaselineEval:
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
        commands = ["cmd1", "cmd2", "cmd3"]
        results = [(0, "ok", "") for _ in range(3)]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            baseline = run_baseline_eval(Path("/fake/worktree"), commands)

        assert baseline == {"cmd1": True, "cmd2": True, "cmd3": True}

    def test_runs_all_commands_even_when_some_fail(self) -> None:
        commands = ["cmd1", "cmd2", "cmd3"]
        results = [
            (0, "ok", ""),  # cmd1 passes
            (1, "fail", ""),  # cmd2 fails
            (0, "ok", ""),  # cmd3 passes — should still run
        ]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            baseline = run_baseline_eval(Path("/fake/worktree"), commands)

        # All three commands must have been called
        assert mock.call_count == 3
        assert baseline == {"cmd1": True, "cmd2": False, "cmd3": True}

    def test_all_fail(self) -> None:
        commands = ["cmd1", "cmd2"]
        results = [(1, "fail", ""), (2, "error", "")]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            baseline = run_baseline_eval(Path("/fake/worktree"), commands)

        assert baseline == {"cmd1": False, "cmd2": False}

    def test_file_not_found_treated_as_failure(self) -> None:
        commands = ["nonexistent"]
        mock = MagicMock(side_effect=FileNotFoundError("not found"))

        with patch("action_harness.evaluator.subprocess.run", mock):
            baseline = run_baseline_eval(Path("/fake/worktree"), commands)

        assert baseline == {"nonexistent": False}


class TestRunEvalWithBaseline:
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

    def test_pre_existing_failure_does_not_cause_eval_failure(self) -> None:
        """Command that was failing at baseline and still fails is NOT a regression."""
        commands = ["cmd1", "cmd2"]
        baseline = {"cmd1": True, "cmd2": False}  # cmd2 was already failing
        results = [
            (0, "ok", ""),  # cmd1 still passes
            (1, "fail", ""),  # cmd2 still fails — pre-existing
        ]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            result = run_eval(Path("/fake/worktree"), eval_commands=commands, baseline=baseline)

        assert result.success is True
        assert "cmd2" in result.pre_existing_failures
        assert result.failed_command is None

    def test_regression_causes_eval_failure(self) -> None:
        """Command that was passing at baseline but now fails IS a regression."""
        commands = ["cmd1", "cmd2"]
        baseline = {"cmd1": True, "cmd2": True}  # both were passing
        results = [
            (0, "ok", ""),  # cmd1 passes
            (1, "fail", ""),  # cmd2 now fails — regression!
        ]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            result = run_eval(Path("/fake/worktree"), eval_commands=commands, baseline=baseline)

        assert result.success is False
        assert result.failed_command == "cmd2"
        assert result.feedback_prompt is not None
        assert result.pre_existing_failures == []

    def test_worker_fixed_pre_existing_issue(self) -> None:
        """Command that was failing at baseline but now passes — worker fixed it."""
        commands = ["cmd1", "cmd2"]
        baseline = {"cmd1": True, "cmd2": False}  # cmd2 was failing
        results = [
            (0, "ok", ""),  # cmd1 passes
            (0, "ok", ""),  # cmd2 now passes — worker fixed it!
        ]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            result = run_eval(Path("/fake/worktree"), eval_commands=commands, baseline=baseline)

        assert result.success is True
        assert result.pre_existing_failures == []
        assert result.commands_passed == 2

    def test_regression_with_pre_existing_failures_mixed(self) -> None:
        """Regression detected alongside pre-existing failures."""
        commands = ["cmd1", "cmd2", "cmd3"]
        baseline = {"cmd1": True, "cmd2": False, "cmd3": True}
        results = [
            (1, "fail", ""),  # cmd1 was passing, now fails — regression
            (1, "fail", ""),  # cmd2 was failing, still fails — pre-existing
            (0, "ok", ""),  # cmd3 still passes
        ]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            result = run_eval(Path("/fake/worktree"), eval_commands=commands, baseline=baseline)

        assert result.success is False
        assert result.failed_command == "cmd1"
        assert "cmd2" in result.pre_existing_failures
        assert result.feedback_prompt is not None

    def test_no_baseline_preserves_original_behavior(self) -> None:
        """Without baseline, run_eval stops on first failure (original behavior)."""
        commands = ["cmd1", "cmd2", "cmd3"]
        results = [
            (0, "ok", ""),
            (1, "fail", ""),
        ]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            result = run_eval(Path("/fake/worktree"), eval_commands=commands)

        assert result.success is False
        assert result.failed_command == "cmd2"
        # Should have stopped after cmd2 — cmd3 never ran
        assert mock.call_count == 2

    def test_multiple_regressions_only_first_feedback_captured(self) -> None:
        """When multiple commands regress, only the first regression's feedback is used."""
        commands = ["cmd1", "cmd2", "cmd3"]
        baseline = {"cmd1": True, "cmd2": True, "cmd3": True}
        results = [
            (1, "fail1", "err1"),  # cmd1 regresses
            (1, "fail2", "err2"),  # cmd2 also regresses
            (0, "ok", ""),  # cmd3 passes
        ]
        mock = self._make_mock(results)

        with patch("action_harness.evaluator.subprocess.run", mock):
            result = run_eval(Path("/fake/worktree"), eval_commands=commands, baseline=baseline)

        assert result.success is False
        # First regression reported
        assert result.failed_command == "cmd1"
        assert result.feedback_prompt is not None
        assert "cmd1" in result.feedback_prompt
        # All commands still ran (baseline mode continues to find pre-existing)
        assert mock.call_count == 3
        assert result.commands_passed == 1
