"""Tests for GitHub issue intake module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from action_harness.issue_intake import (
    build_issue_prompt,
    detect_openspec_change,
    read_issue,
)
from action_harness.models import ValidationError


class TestReadIssue:
    """Tests for read_issue function."""

    def _mock_gh(
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

    def test_success(self, tmp_path: Path) -> None:
        data = json.dumps({"title": "Fix bug", "body": "Details...", "state": "OPEN"})
        mock = self._mock_gh(stdout=data)
        with patch("action_harness.issue_intake.subprocess.run", mock):
            issue = read_issue(42, tmp_path)
        assert issue.title == "Fix bug"
        assert issue.body == "Details..."
        assert issue.state == "OPEN"

    def test_issue_not_found(self, tmp_path: Path) -> None:
        mock = self._mock_gh(returncode=1, stderr="not found")
        with patch("action_harness.issue_intake.subprocess.run", mock):
            with pytest.raises(ValidationError, match="Issue #42 not found"):
                read_issue(42, tmp_path)

    def test_issue_closed(self, tmp_path: Path) -> None:
        data = json.dumps({"title": "Old bug", "body": "Fixed.", "state": "CLOSED"})
        mock = self._mock_gh(stdout=data)
        with patch("action_harness.issue_intake.subprocess.run", mock):
            with pytest.raises(ValidationError, match="already closed"):
                read_issue(42, tmp_path)


class TestDetectOpenspecChange:
    """Tests for detect_openspec_change function."""

    def test_openspec_colon_pattern(self, tmp_path: Path) -> None:
        change_dir = tmp_path / "openspec" / "changes" / "add-logging"
        change_dir.mkdir(parents=True)
        result = detect_openspec_change("See openspec:add-logging", tmp_path)
        assert result == "add-logging"

    def test_change_colon_pattern(self, tmp_path: Path) -> None:
        change_dir = tmp_path / "openspec" / "changes" / "fix-auth"
        change_dir.mkdir(parents=True)
        result = detect_openspec_change("change: fix-auth", tmp_path)
        assert result == "fix-auth"

    def test_path_pattern(self, tmp_path: Path) -> None:
        change_dir = tmp_path / "openspec" / "changes" / "new-feature"
        change_dir.mkdir(parents=True)
        result = detect_openspec_change("openspec/changes/new-feature/", tmp_path)
        assert result == "new-feature"

    def test_pattern_found_but_dir_missing(self, tmp_path: Path) -> None:
        result = detect_openspec_change("See openspec:nonexistent", tmp_path)
        assert result is None

    def test_no_pattern_returns_none(self, tmp_path: Path) -> None:
        result = detect_openspec_change("Just a regular issue body", tmp_path)
        assert result is None

    def test_multiple_patterns_returns_first(self, tmp_path: Path) -> None:
        # Create both directories
        (tmp_path / "openspec" / "changes" / "first").mkdir(parents=True)
        (tmp_path / "openspec" / "changes" / "second").mkdir(parents=True)
        body = "See openspec:first and also openspec:second"
        result = detect_openspec_change(body, tmp_path)
        assert result == "first"


class TestBuildIssuePrompt:
    """Tests for build_issue_prompt function."""

    def test_basic_prompt(self) -> None:
        result = build_issue_prompt(42, "Fix bug", "Details")
        assert result == "# GitHub Issue #42: Fix bug\n\nDetails"
