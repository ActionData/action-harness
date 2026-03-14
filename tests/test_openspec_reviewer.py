"""Tests for the OpenSpec review agent module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from action_harness.openspec_reviewer import (
    build_review_prompt,
    dispatch_openspec_review,
    parse_review_result,
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
        assert '"tasks_complete"' in prompt
        assert '"validation_passed"' in prompt
        assert '"semantic_review_passed"' in prompt
        assert '"findings"' in prompt
        assert '"archived"' in prompt

    def test_change_name_interpolated_in_paths(self) -> None:
        prompt = build_review_prompt("test-feature")
        assert "openspec/changes/test-feature/tasks.md" in prompt


class TestDispatchOpenspecReview:
    def test_claude_cli_invocation_args(self, tmp_path: Path) -> None:
        """Verify claude CLI is invoked with correct arguments."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "result": json.dumps(
                    {
                        "status": "approved",
                        "tasks_total": 5,
                        "tasks_complete": 5,
                        "validation_passed": True,
                        "semantic_review_passed": True,
                        "findings": [],
                        "archived": True,
                    }
                )
            }
        )
        mock_result.stderr = ""

        # Mock count_commits_ahead to return 0 (no push needed)
        with (
            patch("action_harness.openspec_reviewer.subprocess.run", return_value=mock_result),
            patch("action_harness.openspec_reviewer.count_commits_ahead", return_value=0),
        ):
            dispatch_openspec_review(
                "test-change",
                tmp_path,
                base_branch="main",
                max_turns=50,
                permission_mode="bypassPermissions",
            )

        # Re-test with proper mock access to verify call args
        mock_run = MagicMock(return_value=mock_result)
        with (
            patch("action_harness.openspec_reviewer.subprocess.run", mock_run),
            patch("action_harness.openspec_reviewer.count_commits_ahead", return_value=0),
        ):
            dispatch_openspec_review(
                "test-change",
                tmp_path,
                base_branch="main",
                max_turns=50,
                permission_mode="bypassPermissions",
            )

        # Check the command that was passed
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "--system-prompt" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--max-turns" in cmd
        assert "50" in cmd
        assert "--permission-mode" in cmd
        assert "bypassPermissions" in cmd

        # Check cwd
        assert mock_run.call_args[1]["cwd"] == tmp_path

    def test_failed_cli_returns_error(self, tmp_path: Path) -> None:
        """When claude CLI returns non-zero, result is failure."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "some error"

        with patch("action_harness.openspec_reviewer.subprocess.run", return_value=mock_result):
            result = dispatch_openspec_review("test-change", tmp_path)

        assert result.success is False
        assert "exited with code 1" in (result.error or "")


class TestParseReviewResult:
    def test_approved_result(self) -> None:
        raw = json.dumps(
            {
                "status": "approved",
                "tasks_total": 5,
                "tasks_complete": 5,
                "validation_passed": True,
                "semantic_review_passed": True,
                "findings": [],
                "archived": True,
            }
        )
        result = parse_review_result(raw, 10.0)
        assert result.success is True
        assert result.tasks_total == 5
        assert result.tasks_complete == 5
        assert result.validation_passed is True
        assert result.semantic_review_passed is True
        assert result.findings == []
        assert result.archived is True
        assert result.duration_seconds == 10.0

    def test_findings_result(self) -> None:
        raw = json.dumps(
            {
                "status": "findings",
                "tasks_total": 5,
                "tasks_complete": 3,
                "validation_passed": True,
                "semantic_review_passed": False,
                "findings": ["Task 4 incomplete", "Task 5 incomplete"],
                "archived": False,
            }
        )
        result = parse_review_result(raw, 8.0)
        assert result.success is False
        assert result.tasks_total == 5
        assert result.tasks_complete == 3
        assert result.findings == ["Task 4 incomplete", "Task 5 incomplete"]
        assert result.archived is False

    def test_malformed_json(self) -> None:
        result = parse_review_result("not json at all {{{", 5.0)
        assert result.success is False
        assert "Failed to parse" in (result.error or "")

    def test_none_output(self) -> None:
        result = parse_review_result(None, 3.0)
        assert result.success is False
        assert "Failed to parse" in (result.error or "")

    def test_json_in_markdown_code_block(self) -> None:
        raw = """Here is my analysis:

```json
{
  "status": "approved",
  "tasks_total": 3,
  "tasks_complete": 3,
  "validation_passed": true,
  "semantic_review_passed": true,
  "findings": [],
  "archived": true
}
```"""
        result = parse_review_result(raw, 7.0)
        assert result.success is True
        assert result.tasks_total == 3
        assert result.archived is True

    def test_empty_string_output(self) -> None:
        result = parse_review_result("", 2.0)
        assert result.success is False
        assert "Failed to parse" in (result.error or "")
