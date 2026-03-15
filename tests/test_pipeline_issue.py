"""Tests for pipeline behavior with issue_number (GitHub issue intake)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from action_harness.pipeline import run_pipeline


def _make_subprocess_mock(
    issue_label_rc: int = 0,
    eval_pass: bool = True,
) -> MagicMock:
    """Create a subprocess mock that handles all pipeline stages.

    Args:
        issue_label_rc: Return code for gh issue edit/comment calls.
        eval_pass: If False, eval commands always fail (no retries will help).
    """
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
            result.returncode = issue_label_rc
            result.stderr = "label error" if issue_label_rc != 0 else ""
            result.stdout = ""
        elif cmd[0] == "gh" and "pr" in cmd and "comment" in cmd:
            result.stdout = ""
        else:
            # Eval commands
            if not eval_pass:
                result.returncode = 1
                result.stdout = "FAIL"
                result.stderr = "test failed"
            else:
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


def _get_call_index(mock: MagicMock, cmd_fragment: str) -> int:
    """Find the index of the first call containing cmd_fragment in args."""
    for i, c in enumerate(mock.call_args_list):
        if cmd_fragment in str(c[0][0]):
            return i
    return -1


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
        mock = _make_subprocess_mock(issue_label_rc=1)

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

    def test_in_progress_labeled_before_worker(self, tmp_path: Path) -> None:
        """harness:in-progress is labeled before the worker dispatch."""
        repo = _setup_fake_repo(tmp_path)
        mock = _make_subprocess_mock()

        with patch("subprocess.run", mock):
            run_pipeline(
                change_name="test-change",
                repo=repo,
                max_retries=0,
                prompt="Fix bug",
                issue_number=42,
                skip_review=True,
            )

        in_progress_idx = _get_call_index(mock, "harness:in-progress")
        claude_idx = _get_call_index(mock, "claude")
        assert in_progress_idx != -1, "harness:in-progress label call not found"
        assert claude_idx != -1, "claude call not found"
        assert in_progress_idx < claude_idx, (
            f"harness:in-progress (index {in_progress_idx}) should come before "
            f"claude worker (index {claude_idx})"
        )

    def test_pr_created_labeled_after_pr(self, tmp_path: Path) -> None:
        """harness:pr-created is labeled after gh pr create."""
        repo = _setup_fake_repo(tmp_path)
        mock = _make_subprocess_mock()

        with patch("subprocess.run", mock):
            run_pipeline(
                change_name="test-change",
                repo=repo,
                max_retries=0,
                prompt="Fix bug",
                issue_number=42,
                skip_review=True,
            )

        pr_create_idx = _get_call_index(mock, "gh pr create")
        # gh pr create is passed as list, so check differently
        pr_create_idx = -1
        pr_created_label_idx = -1
        for i, c in enumerate(mock.call_args_list):
            cmd = c[0][0]
            if cmd[0] == "gh" and "pr" in cmd and "create" in cmd:
                pr_create_idx = i
            if cmd[0] == "gh" and "issue" in cmd and "harness:pr-created" in str(cmd):
                pr_created_label_idx = i

        assert pr_create_idx != -1, "gh pr create call not found"
        assert pr_created_label_idx != -1, "harness:pr-created label call not found"
        assert pr_created_label_idx > pr_create_idx, (
            f"harness:pr-created (index {pr_created_label_idx}) should come after "
            f"gh pr create (index {pr_create_idx})"
        )

    def test_failure_labels_harness_failed(self, tmp_path: Path) -> None:
        """Pipeline labels issue with harness:failed when pipeline fails."""
        repo = _setup_fake_repo(tmp_path)
        mock = _make_subprocess_mock(eval_pass=False)

        with patch("subprocess.run", mock):
            pr_result, _ = run_pipeline(
                change_name="test-change",
                repo=repo,
                max_retries=0,
                prompt="Fix bug",
                issue_number=42,
                skip_review=True,
            )

        assert not pr_result.success
        gh_issue_calls = _get_gh_issue_calls(mock)

        label_calls = [c for c in gh_issue_calls if "edit" in c and "--add-label" in c]
        assert any("harness:failed" in c for c in label_calls), (
            f"Expected harness:failed label on failure, got: {label_calls}"
        )
        # Should also have in-progress from before the failure
        assert any("harness:in-progress" in c for c in label_calls)

    def test_no_failure_label_when_successful(self, tmp_path: Path) -> None:
        """Successful pipeline does not apply harness:failed label."""
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
        assert not any("harness:failed" in c for c in label_calls)
