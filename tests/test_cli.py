"""Tests for CLI entrypoint and input validation."""

from pathlib import Path
from unittest.mock import patch

import pytest

from action_harness.cli import ValidationError, validate_inputs


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Create a minimal fake git repo with an OpenSpec change directory."""
    (tmp_path / ".git").mkdir()
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    return tmp_path


def test_valid_inputs(fake_repo: Path) -> None:
    with patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"):
        validate_inputs("test-change", fake_repo)


def test_missing_repo() -> None:
    with pytest.raises(ValidationError, match="Repository path does not exist"):
        validate_inputs("anything", Path("/nonexistent/repo/path"))


def test_not_a_git_repo(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="Not a git repository"):
        validate_inputs("anything", tmp_path)


def test_missing_change_dir(fake_repo: Path) -> None:
    with pytest.raises(ValidationError, match="Change directory not found"):
        validate_inputs("nonexistent-change", fake_repo)


def test_missing_claude_cli(fake_repo: Path) -> None:
    def selective_which(cmd: str) -> str | None:
        if cmd == "claude":
            return None
        return "/usr/bin/mock"

    with patch("action_harness.cli.shutil.which", side_effect=selective_which):
        with pytest.raises(ValidationError, match="claude CLI not found"):
            validate_inputs("test-change", fake_repo)


def test_missing_gh_cli(fake_repo: Path) -> None:
    def selective_which(cmd: str) -> str | None:
        if cmd == "gh":
            return None
        return "/usr/bin/mock"

    with patch("action_harness.cli.shutil.which", side_effect=selective_which):
        with pytest.raises(ValidationError, match="gh CLI not found"):
            validate_inputs("test-change", fake_repo)
