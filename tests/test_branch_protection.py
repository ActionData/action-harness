"""Tests for branch protection checks."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from action_harness.branch_protection import check_branch_protection


def _make_completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_branch_protection_enabled(tmp_path: Path) -> None:
    """gh reports branch protection is enabled."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
        cwd=tmp_path,
        capture_output=True,
    )

    with patch("action_harness.branch_protection.subprocess.run") as mock_run:
        # auth check succeeds, API returns protection
        mock_run.side_effect = [
            _make_completed(0),  # gh auth status
            _make_completed(0, stdout="https://github.com/test/repo.git"),  # git remote
            _make_completed(1, stderr="fatal: ref"),  # git symbolic-ref
            _make_completed(0, stdout='{"required_status_checks": {}}'),  # gh api
        ]
        result = check_branch_protection(tmp_path)
        assert result is True


def test_branch_protection_not_configured(tmp_path: Path) -> None:
    """gh reports no branch protection (404)."""
    with patch("action_harness.branch_protection.subprocess.run") as mock_run:
        mock_run.side_effect = [
            _make_completed(0),  # gh auth status
            _make_completed(0, stdout="https://github.com/test/repo.git"),  # git remote
            _make_completed(1, stderr="fatal"),  # git symbolic-ref
            _make_completed(1, stderr="404 Not Found"),  # gh api
        ]
        result = check_branch_protection(tmp_path)
        assert result is False


def test_gh_not_available(tmp_path: Path) -> None:
    """gh CLI not found returns None."""
    with patch("action_harness.branch_protection.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("gh not found")
        result = check_branch_protection(tmp_path)
        assert result is None


def test_gh_not_authenticated(tmp_path: Path) -> None:
    """gh not authenticated returns None."""
    with patch("action_harness.branch_protection.subprocess.run") as mock_run:
        mock_run.return_value = _make_completed(1, stderr="not logged in")
        result = check_branch_protection(tmp_path)
        assert result is None
