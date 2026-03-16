"""Tests for branch protection checks."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from action_harness.branch_protection import check_branch_protection


def _make_completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _command_aware_mock(
    responses: dict[str, subprocess.CompletedProcess[str]],
) -> object:
    """Create a side_effect that dispatches based on the first arg."""

    def side_effect(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if cmd[0] == "gh" and cmd[1] == "auth":
            return responses.get("gh_auth", _make_completed(0))
        if cmd[0] == "git" and "remote" in cmd:
            return responses.get(
                "git_remote",
                _make_completed(0, stdout="https://github.com/test/repo.git"),
            )
        if cmd[0] == "git" and "symbolic-ref" in cmd:
            return responses.get("git_symbolic", _make_completed(1, stderr="fatal"))
        if cmd[0] == "gh" and cmd[1] == "api":
            return responses.get("gh_api", _make_completed(0))
        return _make_completed(0)

    return side_effect


def test_branch_protection_enabled(tmp_path: Path) -> None:
    """gh reports branch protection is enabled."""
    responses = {
        "gh_auth": _make_completed(0),
        "git_remote": _make_completed(0, stdout="https://github.com/test/repo.git"),
        "gh_api": _make_completed(0, stdout='{"required_status_checks": {}}'),
    }

    with patch(
        "action_harness.branch_protection.subprocess.run",
        side_effect=_command_aware_mock(responses),
    ):
        result = check_branch_protection(tmp_path)
        assert result is True


def test_branch_protection_not_configured(tmp_path: Path) -> None:
    """gh reports no branch protection (404)."""
    responses = {
        "gh_auth": _make_completed(0),
        "git_remote": _make_completed(0, stdout="https://github.com/test/repo.git"),
        "gh_api": _make_completed(1, stderr="404 Not Found"),
    }

    with patch(
        "action_harness.branch_protection.subprocess.run",
        side_effect=_command_aware_mock(responses),
    ):
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


def test_ssh_non_github_returns_none(tmp_path: Path) -> None:
    """SSH remote to non-GitHub host returns None (no spurious API calls)."""
    responses = {
        "gh_auth": _make_completed(0),
        "git_remote": _make_completed(0, stdout="git@gitlab.com:owner/repo.git"),
    }

    with patch(
        "action_harness.branch_protection.subprocess.run",
        side_effect=_command_aware_mock(responses),
    ):
        result = check_branch_protection(tmp_path)
        assert result is None
