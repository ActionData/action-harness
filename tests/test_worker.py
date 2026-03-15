"""Tests for Claude Code CLI dispatch. Mocks subprocess.run — no real Claude Code."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from action_harness.models import WorkerResult
from action_harness.progress import PROGRESS_FILENAME
from action_harness.worker import (
    build_system_prompt,
    count_commits_ahead,
    dispatch_worker,
    read_harness_md,
)


def make_mock_subprocess(
    claude_returncode: int = 0,
    claude_stdout: str = "",
    claude_stderr: str = "",
    commits_ahead: int = 1,
) -> MagicMock:
    """Create a mock that handles claude CLI and git rev-list calls."""
    mock = MagicMock()

    def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        if cmd[0] == "claude":
            result.returncode = claude_returncode
            result.stdout = claude_stdout
            result.stderr = claude_stderr
        elif "rev-list" in cmd:
            result.returncode = 0
            result.stdout = f"{commits_ahead}\n"
            result.stderr = ""
        else:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        return result

    mock.side_effect = side_effect
    return mock


def get_claude_cmd(mock: MagicMock) -> list[str]:
    """Extract the claude CLI command from mock call args."""
    for call in mock.call_args_list:
        cmd = call[0][0]
        if cmd[0] == "claude":
            return cmd
    raise AssertionError("claude CLI was never called")


def get_claude_prompt(mock: MagicMock) -> str:
    """Extract the user prompt (-p value) from the claude CLI call."""
    for call in mock.call_args_list:
        cmd = call[0][0]
        if cmd[0] == "claude":
            idx = cmd.index("-p")
            return cmd[idx + 1]
    raise AssertionError("claude CLI was never called")


def get_claude_system_prompt(mock: MagicMock) -> str:
    """Extract the --system-prompt value from the claude CLI call."""
    for call in mock.call_args_list:
        cmd = call[0][0]
        if cmd[0] == "claude" and "--system-prompt" in cmd:
            idx = cmd.index("--system-prompt")
            return cmd[idx + 1]
    raise AssertionError("claude CLI was never called with --system-prompt")


# Default JSON output for tests that don't care about specific values
_OK_JSON = json.dumps({"cost_usd": 0.01, "result": "ok"})


class TestReadHarnessMd:
    def test_returns_contents_when_file_exists(self, tmp_path: Path) -> None:
        (tmp_path / "HARNESS.md").write_text("# Worker Instructions\n\nRun tests first.")
        result = read_harness_md(tmp_path)
        assert result == "# Worker Instructions\n\nRun tests first."

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        result = read_harness_md(tmp_path)
        assert result is None

    def test_returns_none_when_file_empty(self, tmp_path: Path) -> None:
        (tmp_path / "HARNESS.md").write_text("")
        result = read_harness_md(tmp_path)
        assert result is None

    def test_returns_none_when_file_whitespace_only(self, tmp_path: Path) -> None:
        (tmp_path / "HARNESS.md").write_text("   \n\n  \t  \n")
        result = read_harness_md(tmp_path)
        assert result is None

    def test_preserves_special_characters(self, tmp_path: Path) -> None:
        content = "Use {curly braces} and `backticks` and {{template}} syntax"
        (tmp_path / "HARNESS.md").write_text(content)
        result = read_harness_md(tmp_path)
        assert result == content

    def test_preserves_unicode(self, tmp_path: Path) -> None:
        content = "Instructions: émojis 🚀 and ñ and 日本語"
        (tmp_path / "HARNESS.md").write_text(content)
        result = read_harness_md(tmp_path)
        assert result == content

    def test_returns_none_on_permission_error(self, tmp_path: Path) -> None:
        (tmp_path / "HARNESS.md").write_text("content")
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            result = read_harness_md(tmp_path)
        assert result is None

    def test_returns_none_on_encoding_error(self, tmp_path: Path) -> None:
        harness_md = tmp_path / "HARNESS.md"
        # Write raw bytes that are invalid UTF-8
        harness_md.write_bytes(b"\x80\x81\x82\x83")
        result = read_harness_md(tmp_path)
        assert result is None


class TestBuildSystemPrompt:
    def test_includes_change_name(self) -> None:
        prompt = build_system_prompt("add-logging")
        assert "add-logging" in prompt

    def test_includes_opsx_apply(self) -> None:
        prompt = build_system_prompt("test-change")
        assert "opsx:apply" in prompt

    def test_includes_commit_instruction(self) -> None:
        prompt = build_system_prompt("test-change")
        assert "commit" in prompt.lower()

    def test_without_harness_md(self) -> None:
        prompt = build_system_prompt("test-change")
        assert "Repo-Specific Instructions" not in prompt

    def test_with_harness_md(self) -> None:
        harness_content = "Always run pytest before committing."
        prompt = build_system_prompt("test-change", harness_md=harness_content)
        assert "## Repo-Specific Instructions" in prompt
        assert harness_content in prompt

    def test_harness_md_appended_verbatim(self) -> None:
        harness_content = "Use {curly braces} and $dollar signs"
        prompt = build_system_prompt("test-change", harness_md=harness_content)
        assert harness_content in prompt

    def test_harness_md_none_unchanged(self) -> None:
        prompt_without = build_system_prompt("test-change")
        prompt_with_none = build_system_prompt("test-change", harness_md=None)
        assert prompt_without == prompt_with_none

    def test_none_change_name_no_opsx_apply(self) -> None:
        prompt = build_system_prompt(None)
        assert "opsx:apply" not in prompt

    def test_none_change_name_generic_prompt(self) -> None:
        prompt = build_system_prompt(None)
        assert "implementing a task" in prompt

    def test_change_name_still_has_opsx_apply(self) -> None:
        prompt = build_system_prompt("my-change")
        assert "opsx:apply" in prompt

    def test_none_change_name_with_harness_md(self) -> None:
        prompt = build_system_prompt(None, harness_md="Run tests first.")
        assert "implementing a task" in prompt
        assert "## Repo-Specific Instructions" in prompt
        assert "Run tests first." in prompt


class TestCountCommitsAhead:
    def test_counts_commits(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "3\n"
        with patch("action_harness.worker.subprocess.run", return_value=mock_result):
            assert count_commits_ahead(Path("/fake"), "main") == 3

    def test_returns_zero_on_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "fatal: bad ref"
        with patch("action_harness.worker.subprocess.run", return_value=mock_result):
            assert count_commits_ahead(Path("/fake"), "main") == 0

    def test_returns_zero_on_invalid_output(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not-a-number\n"
        with patch("action_harness.worker.subprocess.run", return_value=mock_result):
            assert count_commits_ahead(Path("/fake"), "main") == 0


class TestDispatchWorker:
    def test_successful_dispatch(self) -> None:
        json_output = json.dumps({"cost_usd": 0.15, "result": "implemented feature"})
        mock = make_mock_subprocess(claude_stdout=json_output, commits_ahead=2)

        with patch("action_harness.worker.subprocess.run", mock):
            result = dispatch_worker("test-change", Path("/fake/worktree"))

        assert result.success is True
        assert result.stage == "worker"
        assert result.commits_ahead == 2
        assert result.cost_usd == 0.15
        assert result.worker_output == "implemented feature"
        assert result.error is None
        assert isinstance(result, WorkerResult)

    def test_cli_failure(self) -> None:
        mock = make_mock_subprocess(claude_returncode=1, claude_stderr="something went wrong")

        with patch("action_harness.worker.subprocess.run", mock):
            result = dispatch_worker("test-change", Path("/fake/worktree"))

        assert result.success is False
        assert "exited with code 1" in (result.error or "")
        assert result.duration_seconds is not None
        assert result.cost_usd is None
        assert result.worker_output is None

    def test_no_commits_detected(self) -> None:
        json_output = json.dumps({"cost_usd": 0.10, "result": "did nothing"})
        mock = make_mock_subprocess(claude_stdout=json_output, commits_ahead=0)

        with patch("action_harness.worker.subprocess.run", mock):
            result = dispatch_worker("test-change", Path("/fake/worktree"))

        assert result.success is False
        assert "No commits were produced" in (result.error or "")
        assert result.commits_ahead == 0

    def test_invocation_uses_system_prompt_flag(self) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)

        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("my-change", Path("/fake/wt"), max_turns=50)

        # Find the claude invocation call
        claude_call = None
        for call in mock.call_args_list:
            cmd = call[0][0]
            if cmd[0] == "claude":
                claude_call = call
                break
        assert claude_call is not None
        cmd = claude_call[0][0]
        # Verify --system-prompt flag is used (not just -p for everything)
        assert "--system-prompt" in cmd
        assert "--output-format" in cmd
        idx = cmd.index("--max-turns")
        assert cmd[idx + 1] == "50"
        assert claude_call[1]["cwd"] == Path("/fake/wt")

    def test_base_branch_passed_to_commit_count(self) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON, commits_ahead=1)

        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("test-change", Path("/fake/wt"), base_branch="develop")

        # Find the rev-list call and verify base_branch is used
        for call in mock.call_args_list:
            cmd = call[0][0]
            if "rev-list" in cmd:
                assert "develop..HEAD" in cmd
                break
        else:
            raise AssertionError("git rev-list was never called")

    def test_invalid_json_output(self) -> None:
        mock = make_mock_subprocess(claude_stdout="not valid json", commits_ahead=1)

        with patch("action_harness.worker.subprocess.run", mock):
            result = dispatch_worker("test-change", Path("/fake/worktree"))

        assert result.success is True
        assert result.worker_output == "not valid json"
        assert result.cost_usd is None

    def test_duration_tracked(self) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)

        with patch("action_harness.worker.subprocess.run", mock):
            result = dispatch_worker("test-change", Path("/fake/worktree"))

        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0

    def test_model_flag_present(self) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", Path("/fake"), model="opus")
        cmd = get_claude_cmd(mock)
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "opus"

    def test_model_flag_absent(self) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", Path("/fake"))
        cmd = get_claude_cmd(mock)
        assert "--model" not in cmd

    def test_effort_flag_present(self) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", Path("/fake"), effort="high")
        cmd = get_claude_cmd(mock)
        idx = cmd.index("--effort")
        assert cmd[idx + 1] == "high"

    def test_effort_flag_absent(self) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", Path("/fake"))
        cmd = get_claude_cmd(mock)
        assert "--effort" not in cmd

    def test_budget_flag_present(self) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", Path("/fake"), max_budget_usd=5.0)
        cmd = get_claude_cmd(mock)
        idx = cmd.index("--max-budget-usd")
        assert cmd[idx + 1] == "5.0"

    def test_budget_flag_absent(self) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", Path("/fake"))
        cmd = get_claude_cmd(mock)
        assert "--max-budget-usd" not in cmd

    def test_permission_mode_default(self) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", Path("/fake"))
        cmd = get_claude_cmd(mock)
        idx = cmd.index("--permission-mode")
        assert cmd[idx + 1] == "bypassPermissions"

    def test_permission_mode_custom(self) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", Path("/fake"), permission_mode="plan")
        cmd = get_claude_cmd(mock)
        idx = cmd.index("--permission-mode")
        assert cmd[idx + 1] == "plan"

    def test_session_id_and_context_usage_captured(self) -> None:
        json_output = json.dumps(
            {
                "session_id": "sess_xyz",
                "cost_usd": 0.1,
                "result": "ok",
                "usage": {"input_tokens": 50000, "output_tokens": 20000},
                "modelUsage": {
                    "claude-opus-4-6[1m]": {
                        "contextWindow": 1000000,
                        "inputTokens": 50000,
                        "outputTokens": 20000,
                        "costUSD": 0.1,
                    }
                },
            }
        )
        mock = make_mock_subprocess(claude_stdout=json_output)
        with patch("action_harness.worker.subprocess.run", mock):
            result = dispatch_worker("t", Path("/fake"))
        assert result.session_id == "sess_xyz"
        assert result.context_usage_pct == pytest.approx(0.07)

    def test_fresh_dispatch_includes_system_prompt_no_resume(self) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", Path("/fake"))
        cmd = get_claude_cmd(mock)
        assert "--system-prompt" in cmd
        assert "--resume" not in cmd

    def test_resume_dispatch_includes_resume_no_system_prompt(self) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", Path("/fake"), session_id="sess_abc", feedback="fix the tests")
        cmd = get_claude_cmd(mock)
        assert "--resume" in cmd
        idx = cmd.index("--resume")
        assert cmd[idx + 1] == "sess_abc"
        assert "--system-prompt" not in cmd
        # User prompt should be just the feedback
        prompt_idx = cmd.index("-p")
        assert cmd[prompt_idx + 1] == "fix the tests"

    def test_resume_without_feedback_raises(self) -> None:
        with pytest.raises(ValueError, match="resume requires feedback"):
            dispatch_worker("t", Path("/fake"), session_id="sess_abc", feedback=None)

    def test_session_id_captured_on_failure(self) -> None:
        json_output = json.dumps(
            {
                "session_id": "sess_fail",
                "cost_usd": 0.05,
                "result": "error",
            }
        )
        mock = make_mock_subprocess(
            claude_returncode=1, claude_stdout=json_output, claude_stderr="oops"
        )
        with patch("action_harness.worker.subprocess.run", mock):
            result = dispatch_worker("t", Path("/fake"))
        assert result.success is False
        assert result.session_id == "sess_fail"

    def test_session_id_captured_on_no_commits(self) -> None:
        json_output = json.dumps(
            {
                "session_id": "sess_nocommit",
                "cost_usd": 0.05,
                "result": "did nothing",
            }
        )
        mock = make_mock_subprocess(claude_stdout=json_output, commits_ahead=0)
        with patch("action_harness.worker.subprocess.run", mock):
            result = dispatch_worker("t", Path("/fake"))
        assert result.success is False
        assert result.session_id == "sess_nocommit"

    def test_context_usage_without_model_usage(self) -> None:
        """When modelUsage is missing, context_window defaults to 1M."""
        json_output = json.dumps(
            {
                "session_id": "sess_x",
                "cost_usd": 0.01,
                "result": "ok",
                "usage": {"input_tokens": 100000, "output_tokens": 50000},
            }
        )
        mock = make_mock_subprocess(claude_stdout=json_output)
        with patch("action_harness.worker.subprocess.run", mock):
            result = dispatch_worker("t", Path("/fake"))
        # 150000 / 1_000_000 = 0.15
        assert result.context_usage_pct == pytest.approx(0.15)

    def test_context_usage_without_usage_key(self) -> None:
        """When usage key is missing, tokens default to 0."""
        json_output = json.dumps(
            {
                "session_id": "sess_x",
                "cost_usd": 0.01,
                "result": "ok",
                "modelUsage": {"model": {"contextWindow": 500000}},
            }
        )
        mock = make_mock_subprocess(claude_stdout=json_output)
        with patch("action_harness.worker.subprocess.run", mock):
            result = dispatch_worker("t", Path("/fake"))
        # 0 / 500000 = 0.0
        assert result.context_usage_pct == pytest.approx(0.0)


class TestDispatchWorkerPromptMode:
    """Tests for dispatch_worker with freeform prompt parameter."""

    def test_prompt_used_as_user_prompt(self, tmp_path: Path) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("prompt-fix-bug", tmp_path, prompt="Fix bug")

        user_prompt = get_claude_prompt(mock)
        assert user_prompt == "Fix bug"

    def test_prompt_mode_uses_generic_system_prompt(self, tmp_path: Path) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("prompt-fix-bug", tmp_path, prompt="Fix bug")

        system_prompt = get_claude_system_prompt(mock)
        assert "opsx:apply" not in system_prompt
        assert "implementing a task" in system_prompt

    def test_no_prompt_uses_opsx_apply(self, tmp_path: Path) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("my-change", tmp_path)

        user_prompt = get_claude_prompt(mock)
        assert "opsx:apply" in user_prompt


class TestProgressFileInjection:
    """Worker prepends .harness-progress.md contents to the user prompt."""

    def test_progress_prepended_when_file_exists(self, tmp_path: Path) -> None:
        progress_content = "# Harness Progress\n\n## Attempt 1\n- **Commits**: 3\n"
        (tmp_path / PROGRESS_FILENAME).write_text(progress_content)

        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", tmp_path)

        prompt = get_claude_prompt(mock)
        assert prompt.startswith(progress_content)
        assert "opsx:apply" in prompt

    def test_prompt_unchanged_when_no_progress(self, tmp_path: Path) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", tmp_path)

        prompt = get_claude_prompt(mock)
        assert prompt.startswith("Implement the OpenSpec change")
        assert PROGRESS_FILENAME not in prompt

    def test_progress_before_task_prompt(self, tmp_path: Path) -> None:
        progress_content = "# Harness Progress\n\n## Attempt 1\n"
        (tmp_path / PROGRESS_FILENAME).write_text(progress_content)

        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", tmp_path, feedback="fix the tests")

        prompt = get_claude_prompt(mock)
        progress_pos = prompt.index("Harness Progress")
        task_pos = prompt.index("opsx:apply")
        assert progress_pos < task_pos

    def test_progress_prepended_in_resume_mode(self, tmp_path: Path) -> None:
        progress_content = "# Harness Progress\n\n## Attempt 1\n"
        (tmp_path / PROGRESS_FILENAME).write_text(progress_content)

        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", tmp_path, session_id="sess_abc", feedback="fix the tests")

        prompt = get_claude_prompt(mock)
        assert prompt.startswith(progress_content)
        assert "fix the tests" in prompt
        # Progress appears before feedback
        progress_pos = prompt.index("Harness Progress")
        feedback_pos = prompt.index("fix the tests")
        assert progress_pos < feedback_pos


class TestHarnessMdInjection:
    """dispatch_worker reads HARNESS.md and injects it into the system prompt."""

    def test_harness_md_injected_into_system_prompt(self, tmp_path: Path) -> None:
        harness_content = "Always run pytest before committing.\nUse typer.echo for logging."
        (tmp_path / "HARNESS.md").write_text(harness_content)

        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", tmp_path)

        system_prompt = get_claude_system_prompt(mock)
        assert "## Repo-Specific Instructions" in system_prompt
        assert harness_content in system_prompt

    def test_no_harness_md_no_repo_specific_section(self, tmp_path: Path) -> None:
        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", tmp_path)

        system_prompt = get_claude_system_prompt(mock)
        assert "Repo-Specific Instructions" not in system_prompt

    def test_harness_md_content_verbatim(self, tmp_path: Path) -> None:
        harness_content = "Use {curly_braces} and $variables and {{templates}}"
        (tmp_path / "HARNESS.md").write_text(harness_content)

        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", tmp_path)

        system_prompt = get_claude_system_prompt(mock)
        assert harness_content in system_prompt

    def test_resume_mode_does_not_inject_harness_md(self, tmp_path: Path) -> None:
        """On resume, HARNESS.md is not re-injected — the session already has it."""
        (tmp_path / "HARNESS.md").write_text("repo instructions")

        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", tmp_path, session_id="sess_abc", feedback="retry")

        cmd = get_claude_cmd(mock)
        assert "--system-prompt" not in cmd
        assert "--resume" in cmd

    def test_harness_md_with_feedback_on_fresh_dispatch(self, tmp_path: Path) -> None:
        """HARNESS.md goes to system prompt, feedback goes to user prompt."""
        harness_content = "Run uv run pytest -v after changes."
        (tmp_path / "HARNESS.md").write_text(harness_content)

        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", tmp_path, feedback="focus on error handling")

        system_prompt = get_claude_system_prompt(mock)
        assert harness_content in system_prompt
        user_prompt = get_claude_prompt(mock)
        assert "focus on error handling" in user_prompt
        assert harness_content not in user_prompt

    def test_harness_md_with_progress_file(self, tmp_path: Path) -> None:
        """HARNESS.md in system prompt and progress in user prompt coexist."""
        harness_content = "Always run tests."
        (tmp_path / "HARNESS.md").write_text(harness_content)
        progress_content = "# Harness Progress\n\n## Attempt 1\n"
        (tmp_path / PROGRESS_FILENAME).write_text(progress_content)

        mock = make_mock_subprocess(claude_stdout=_OK_JSON)
        with patch("action_harness.worker.subprocess.run", mock):
            dispatch_worker("t", tmp_path)

        system_prompt = get_claude_system_prompt(mock)
        assert harness_content in system_prompt
        user_prompt = get_claude_prompt(mock)
        assert progress_content in user_prompt
