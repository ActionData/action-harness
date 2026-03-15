"""Tests for the OpenSpec review agent module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from action_harness.openspec_reviewer import (
    build_review_prompt,
    dispatch_openspec_review,
    parse_review_result,
    push_archive_if_needed,
)


class TestBuildReviewPrompt:
    def test_includes_change_name(self) -> None:
        prompt = build_review_prompt("my-change")
        assert "my-change" in prompt

    def test_includes_openspec_validate(self) -> None:
        prompt = build_review_prompt("my-change")
        assert "openspec validate" in prompt

    def test_includes_openspec_archive(self) -> None:
        prompt = build_review_prompt("my-change")
        assert "openspec archive" in prompt

    def test_includes_deepwiki_reference(self) -> None:
        prompt = build_review_prompt("my-change")
        assert "Fission-AI/OpenSpec" in prompt
        assert "deepwiki" in prompt

    def test_includes_json_output_format(self) -> None:
        prompt = build_review_prompt("my-change")
        assert '"status"' in prompt
        assert '"tasks_total"' in prompt
        assert '"findings"' in prompt
        assert '"archived"' in prompt

    def test_includes_tasks_md_reference(self) -> None:
        prompt = build_review_prompt("my-change")
        assert "tasks.md" in prompt


class TestDispatchOpenspecReview:
    def _mock_subprocess(
        self,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> MagicMock:
        mock = MagicMock()
        result = MagicMock()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        mock.return_value = result
        return mock

    def test_invocation_args(self) -> None:
        mock = self._mock_subprocess(stdout='{"result": "ok"}')

        with patch("action_harness.openspec_reviewer.subprocess.run", mock):
            dispatch_openspec_review("test-change", Path("/fake/wt"))

        mock.assert_called_once()
        call_args = mock.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "--system-prompt" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--permission-mode" in cmd
        idx = cmd.index("--permission-mode")
        assert cmd[idx + 1] == "bypassPermissions"
        assert call_args[1]["cwd"] == Path("/fake/wt")

    def test_custom_permission_mode(self) -> None:
        mock = self._mock_subprocess(stdout='{"result": "ok"}')

        with patch("action_harness.openspec_reviewer.subprocess.run", mock):
            dispatch_openspec_review("test-change", Path("/fake/wt"), permission_mode="plan")

        cmd = mock.call_args[0][0]
        idx = cmd.index("--permission-mode")
        assert cmd[idx + 1] == "plan"

    def test_returns_stdout_and_duration(self) -> None:
        mock = self._mock_subprocess(stdout='{"result": "data"}')

        with patch("action_harness.openspec_reviewer.subprocess.run", mock):
            raw_output, duration = dispatch_openspec_review("test-change", Path("/fake/wt"))

        assert raw_output == '{"result": "data"}'
        assert duration >= 0

    def test_max_turns_passed(self) -> None:
        mock = self._mock_subprocess(stdout='{"result": "ok"}')

        with patch("action_harness.openspec_reviewer.subprocess.run", mock):
            dispatch_openspec_review("test-change", Path("/fake/wt"), max_turns=50)

        cmd = mock.call_args[0][0]
        idx = cmd.index("--max-turns")
        assert cmd[idx + 1] == "50"


class TestParseReviewResult:
    def test_approved_result(self) -> None:
        review_json = {
            "status": "approved",
            "tasks_total": 5,
            "tasks_complete": 5,
            "validation_passed": True,
            "semantic_review_passed": True,
            "findings": [],
            "archived": True,
        }
        raw = json.dumps({"result": json.dumps(review_json)})

        result = parse_review_result(raw, 10.0)

        assert result.success is True
        assert result.stage == "openspec-review"
        assert result.tasks_total == 5
        assert result.tasks_complete == 5
        assert result.validation_passed is True
        assert result.semantic_review_passed is True
        assert result.findings == []
        assert result.archived is True
        assert result.duration_seconds == 10.0

    def test_findings_result(self) -> None:
        review_json = {
            "status": "findings",
            "tasks_total": 5,
            "tasks_complete": 3,
            "validation_passed": False,
            "semantic_review_passed": False,
            "findings": ["Task 1.4 is incomplete", "Task 1.5 is incomplete"],
            "archived": False,
        }
        raw = json.dumps({"result": json.dumps(review_json)})

        result = parse_review_result(raw, 8.0)

        assert result.success is False
        assert result.tasks_total == 5
        assert result.tasks_complete == 3
        assert result.validation_passed is False
        assert result.findings == [
            "Task 1.4 is incomplete",
            "Task 1.5 is incomplete",
        ]
        assert result.archived is False

    def test_malformed_json_from_cli(self) -> None:
        result = parse_review_result("not valid json at all", 5.0)

        assert result.success is False
        assert result.error is not None
        assert "Failed to parse" in result.error

    def test_no_json_block_in_result(self) -> None:
        raw = json.dumps({"result": "I reviewed the code and it looks good."})

        result = parse_review_result(raw, 5.0)

        assert result.success is False
        assert result.error is not None
        assert "Failed to parse" in result.error

    def test_needs_human_result(self) -> None:
        review_json = {
            "status": "needs-human",
            "tasks_total": 10,
            "tasks_complete": 7,
            "human_tasks_remaining": 3,
            "validation_passed": True,
            "semantic_review_passed": True,
            "findings": [
                "3 human tasks remaining: verify API tokens, watch CI run, merge to master"
            ],
            "archived": False,
        }
        raw = json.dumps({"result": json.dumps(review_json)})

        result = parse_review_result(raw, 12.0)

        assert result.success is True
        assert result.human_tasks_remaining == 3
        assert result.tasks_total == 10
        assert result.tasks_complete == 7
        assert result.validation_passed is True
        assert result.archived is False
        assert len(result.findings) == 1
        assert result.duration_seconds == 12.0

    def test_json_embedded_in_prose(self) -> None:
        review_json = {
            "status": "approved",
            "tasks_total": 3,
            "tasks_complete": 3,
            "validation_passed": True,
            "semantic_review_passed": True,
            "findings": [],
            "archived": True,
        }
        result_text = (
            f"I reviewed everything and here is my result:\n```json\n{json.dumps(review_json)}\n```"
        )
        raw = json.dumps({"result": result_text})

        result = parse_review_result(raw, 6.0)

        assert result.success is True
        assert result.tasks_total == 3
        assert result.archived is True


class TestPushArchiveIfNeeded:
    def test_no_new_commits(self) -> None:
        with patch(
            "action_harness.openspec_reviewer.count_commits_ahead",
            return_value=5,
        ):
            pushed, error = push_archive_if_needed(Path("/fake"), "main", commits_before=5)

        assert pushed is False
        assert error is None

    def test_push_succeeds(self) -> None:
        push_mock = MagicMock()
        push_mock.returncode = 0
        push_mock.stdout = ""
        push_mock.stderr = ""

        with (
            patch(
                "action_harness.openspec_reviewer.count_commits_ahead",
                return_value=7,
            ),
            patch(
                "action_harness.openspec_reviewer.subprocess.run",
                return_value=push_mock,
            ),
        ):
            pushed, error = push_archive_if_needed(Path("/fake"), "main", commits_before=5)

        assert pushed is True
        assert error is None

    def test_push_fails(self) -> None:
        push_mock = MagicMock()
        push_mock.returncode = 1
        push_mock.stdout = ""
        push_mock.stderr = "rejected"

        with (
            patch(
                "action_harness.openspec_reviewer.count_commits_ahead",
                return_value=7,
            ),
            patch(
                "action_harness.openspec_reviewer.subprocess.run",
                return_value=push_mock,
            ),
        ):
            pushed, error = push_archive_if_needed(Path("/fake"), "main", commits_before=5)

        assert pushed is False
        assert error is not None
        assert "rejected" in error
