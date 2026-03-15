"""Tests for pipeline behavior with issue_number (GitHub issue intake)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from action_harness.pipeline import run_pipeline


def _make_subprocess_mock() -> MagicMock:
    """Create a subprocess mock that handles all pipeline stages successfully."""
    mock = MagicMock()

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
        elif cmd[0] == "gh" and "issue" in cmd:
            # Issue labeling and commenting - always succeed
            result.stdout = ""
        elif cmd[0] == "gh" and "pr" in cmd and "comment" in cmd:
            result.stdout = ""
        else:
            # Eval commands
            result.stdout = ""
        return result

    mock.side_effect = side_effect
    return mock


def _setup_fake_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repo for pipeline tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


def _get_gh_issue_calls(mock: MagicMock) -> list[list[str]]:
    """Extract all gh issue calls from mock."""
    return [
        c[0][0]
        for c in mock.call_args_list
        if len(c[0][0]) > 1 and c[0][0][0] == "gh" and c[0][0][1] == "issue"
    ]


class TestPipelineIssueLabeling:
    """Tests for issue labeling during pipeline execution."""

    def test_labels_in_progress_at_start(self, tmp_path: Path) -> None:
        """Pipeline labels issue with harness:in-progress after worktree creation."""
        repo = _setup_fake_repo(tmp_path)
        mock = _make_subprocess_mock()

        with patch("subprocess.run", mock):
            pr_result, _ = run_pipeline(
                change_name="test-change",
                repo=repo,
                max_retries=0,
                prompt="Fix bug",
                issue_number=42,
                skip_review=True,
            )

        assert pr_result.success
        gh_issue_calls = _get_gh_issue_calls(mock)

        # Should have label calls
        label_calls = [c for c in gh_issue_calls if "edit" in c and "--add-label" in c]
        assert any("harness:in-progress" in c for c in label_calls), (
            f"Expected harness:in-progress label, got: {label_calls}"
        )

    def test_labels_pr_created_after_pr(self, tmp_path: Path) -> None:
        """Pipeline labels issue with harness:pr-created after PR creation."""
        repo = _setup_fake_repo(tmp_path)
        mock = _make_subprocess_mock()

        with patch("subprocess.run", mock):
            pr_result, _ = run_pipeline(
                change_name="test-change",
                repo=repo,
                max_retries=0,
                prompt="Fix bug",
                issue_number=42,
                skip_review=True,
            )

        assert pr_result.success
        gh_issue_calls = _get_gh_issue_calls(mock)

        label_calls = [c for c in gh_issue_calls if "edit" in c and "--add-label" in c]
        assert any("harness:pr-created" in c for c in label_calls), (
            f"Expected harness:pr-created label, got: {label_calls}"
        )

    def test_comments_with_pr_url(self, tmp_path: Path) -> None:
        """Pipeline comments on issue with PR URL after PR creation."""
        repo = _setup_fake_repo(tmp_path)
        mock = _make_subprocess_mock()

        with patch("subprocess.run", mock):
            pr_result, _ = run_pipeline(
                change_name="test-change",
                repo=repo,
                max_retries=0,
                prompt="Fix bug",
                issue_number=42,
                skip_review=True,
            )

        assert pr_result.success
        gh_issue_calls = _get_gh_issue_calls(mock)

        comment_calls = [c for c in gh_issue_calls if "comment" in c]
        assert any("PR created:" in " ".join(c) for c in comment_calls), (
            f"Expected comment with PR URL, got: {comment_calls}"
        )

    def test_no_issue_labels_when_issue_none(self, tmp_path: Path) -> None:
        """Pipeline does not label issues when issue_number is None."""
        repo = _setup_fake_repo(tmp_path)
        mock = _make_subprocess_mock()

        with patch("subprocess.run", mock):
            pr_result, _ = run_pipeline(
                change_name="test-change",
                repo=repo,
                max_retries=0,
                prompt="Fix bug",
                issue_number=None,
                skip_review=True,
            )

        assert pr_result.success
        gh_issue_calls = _get_gh_issue_calls(mock)
        assert len(gh_issue_calls) == 0

    def test_label_failure_does_not_fail_pipeline(self, tmp_path: Path) -> None:
        """Pipeline succeeds even if issue labeling fails."""
        repo = _setup_fake_repo(tmp_path)
        mock = MagicMock()

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
            elif cmd[0] == "gh" and "issue" in cmd:
                # Issue labeling FAILS
                result.returncode = 1
                result.stderr = "label not found"
                result.stdout = ""
            elif cmd[0] == "gh" and "pr" in cmd and "comment" in cmd:
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        mock.side_effect = side_effect

        with patch("subprocess.run", mock):
            pr_result, _ = run_pipeline(
                change_name="test-change",
                repo=repo,
                max_retries=0,
                prompt="Fix bug",
                issue_number=42,
                skip_review=True,
            )

        # Pipeline should still succeed even though labeling failed
        assert pr_result.success
