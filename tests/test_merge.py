"""Tests for merge logic: merge_pr, check_merge_gates, wait_for_ci, post_merge_blocked_comment."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from action_harness.merge import (
    check_merge_gates,
    merge_pr,
    post_merge_blocked_comment,
    wait_for_ci,
)


class TestMergePr:
    def test_success(self, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Merged"

        with patch("action_harness.merge.subprocess.run", return_value=mock_result) as mock_run:
            result = merge_pr("https://github.com/org/repo/pull/1", tmp_path)

        assert result.success is True
        assert result.merged is True
        assert result.error is None
        # Verify gh command was called correctly
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "gh" in cmd
        assert "pr" in cmd
        assert "merge" in cmd
        assert "--merge" in cmd
        assert "--delete-branch" in cmd

    def test_failure(self, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "pull request is not mergeable"
        mock_result.stdout = ""

        with patch("action_harness.merge.subprocess.run", return_value=mock_result):
            result = merge_pr("https://github.com/org/repo/pull/1", tmp_path)

        assert result.success is False
        assert result.merged is False
        assert "not mergeable" in (result.error or "")

    def test_no_delete_branch(self, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("action_harness.merge.subprocess.run", return_value=mock_result) as mock_run:
            merge_pr("https://github.com/org/repo/pull/1", tmp_path, delete_branch=False)

        cmd = mock_run.call_args[0][0]
        assert "--delete-branch" not in cmd

    def test_file_not_found(self, tmp_path: Path) -> None:
        with patch(
            "action_harness.merge.subprocess.run",
            side_effect=FileNotFoundError("gh not found"),
        ):
            result = merge_pr("https://github.com/org/repo/pull/1", tmp_path)

        assert result.success is False
        assert result.merged is False


class TestCheckMergeGates:
    def test_all_pass(self) -> None:
        gates, all_passed = check_merge_gates(
            protected_files=[],
            findings_remain=False,
            openspec_review_passed=True,
            skip_review=False,
        )
        assert all_passed is True
        assert gates == {
            "no_protected_files": True,
            "review_clean": True,
            "openspec_review_passed": True,
        }

    def test_protected_files_blocks(self) -> None:
        gates, all_passed = check_merge_gates(
            protected_files=["CLAUDE.md"],
            findings_remain=False,
            openspec_review_passed=True,
            skip_review=False,
        )
        assert all_passed is False
        assert gates["no_protected_files"] is False
        # Other gates should still be evaluated
        assert gates["review_clean"] is True
        assert gates["openspec_review_passed"] is True

    def test_findings_remain_blocks(self) -> None:
        gates, all_passed = check_merge_gates(
            protected_files=[],
            findings_remain=True,
            openspec_review_passed=True,
            skip_review=False,
        )
        assert all_passed is False
        assert gates["review_clean"] is False

    def test_openspec_fails_blocks(self) -> None:
        gates, all_passed = check_merge_gates(
            protected_files=[],
            findings_remain=False,
            openspec_review_passed=False,
            skip_review=False,
        )
        assert all_passed is False
        assert gates["openspec_review_passed"] is False

    def test_skip_review_makes_review_clean(self) -> None:
        gates, all_passed = check_merge_gates(
            protected_files=[],
            findings_remain=True,
            openspec_review_passed=True,
            skip_review=True,
        )
        assert all_passed is True
        assert gates["review_clean"] is True

    def test_all_gates_evaluated_even_when_first_fails(self) -> None:
        """Verify no short-circuit — all 3 keys present even when first gate fails."""
        gates, all_passed = check_merge_gates(
            protected_files=["pyproject.toml"],
            findings_remain=True,
            openspec_review_passed=False,
            skip_review=False,
        )
        assert all_passed is False
        assert len(gates) == 3
        assert "no_protected_files" in gates
        assert "review_clean" in gates
        assert "openspec_review_passed" in gates


class TestWaitForCi:
    def test_pass(self, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("action_harness.merge.subprocess.run", return_value=mock_result):
            result = wait_for_ci("https://github.com/org/repo/pull/1", tmp_path)

        assert result is True

    def test_fail(self, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "checks failed"

        with patch("action_harness.merge.subprocess.run", return_value=mock_result):
            result = wait_for_ci("https://github.com/org/repo/pull/1", tmp_path)

        assert result is False

    def test_timeout(self, tmp_path: Path) -> None:
        with patch(
            "action_harness.merge.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=600),
        ):
            result = wait_for_ci(
                "https://github.com/org/repo/pull/1", tmp_path, timeout_seconds=600
            )

        assert result is False

    def test_custom_timeout_passed_to_subprocess(self, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("action_harness.merge.subprocess.run", return_value=mock_result) as mock_run:
            wait_for_ci("https://github.com/org/repo/pull/1", tmp_path, timeout_seconds=300)

        assert mock_run.call_args[1]["timeout"] == 300


class TestPostMergeBlockedComment:
    def test_posts_correct_body(self, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0

        gates = {
            "no_protected_files": False,
            "review_clean": True,
            "openspec_review_passed": True,
        }

        with patch("action_harness.merge.subprocess.run", return_value=mock_result) as mock_run:
            post_merge_blocked_comment("https://github.com/org/repo/pull/1", tmp_path, gates)

        # Verify the body content
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "gh" in cmd
        assert "pr" in cmd
        assert "comment" in cmd

        body = cmd[cmd.index("--body") + 1]
        assert "Auto-merge blocked" in body
        assert "[ ] No protected files touched" in body
        assert "[x] Review agents clean" in body
        assert "[x] OpenSpec review passed" in body

    def test_failure_does_not_raise(self, tmp_path: Path) -> None:
        """Best-effort: failure logs warning but does not raise."""
        with patch(
            "action_harness.merge.subprocess.run",
            side_effect=FileNotFoundError("gh not found"),
        ):
            # Should not raise
            post_merge_blocked_comment(
                "https://github.com/org/repo/pull/1",
                tmp_path,
                {"no_protected_files": True},
            )

    def test_gh_failure_does_not_raise(self, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "auth required"

        with patch("action_harness.merge.subprocess.run", return_value=mock_result):
            # Should not raise
            post_merge_blocked_comment(
                "https://github.com/org/repo/pull/1",
                tmp_path,
                {"no_protected_files": False},
            )
