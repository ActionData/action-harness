"""Tests for repository management module."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from action_harness.cli import ValidationError
from action_harness.repo import _get_repo_dir, _parse_repo_ref, resolve_repo


class TestParseRepoRef:
    """Test _parse_repo_ref — GitHub shorthand, HTTPS URL, SSH URL."""

    def test_github_shorthand(self) -> None:
        owner, name, url = _parse_repo_ref("user/repo")
        assert owner == "user"
        assert name == "repo"
        assert url == "https://github.com/user/repo.git"

    def test_github_shorthand_with_dots(self) -> None:
        owner, name, url = _parse_repo_ref("my-org/my.repo")
        assert owner == "my-org"
        assert name == "my.repo"
        assert url == "https://github.com/my-org/my.repo.git"

    def test_https_url(self) -> None:
        owner, name, url = _parse_repo_ref("https://github.com/ActionData/action-harness")
        assert owner == "ActionData"
        assert name == "action-harness"
        assert url == "https://github.com/ActionData/action-harness.git"

    def test_https_url_with_git_suffix(self) -> None:
        owner, name, url = _parse_repo_ref("https://github.com/user/repo.git")
        assert owner == "user"
        assert name == "repo"
        assert url == "https://github.com/user/repo.git"

    def test_https_url_with_trailing_slash(self) -> None:
        owner, name, url = _parse_repo_ref("https://github.com/user/repo/")
        assert owner == "user"
        assert name == "repo"
        assert url == "https://github.com/user/repo.git"

    def test_ssh_url(self) -> None:
        owner, name, url = _parse_repo_ref("git@github.com:owner/repo.git")
        assert owner == "owner"
        assert name == "repo"
        assert url == "git@github.com:owner/repo.git"

    def test_ssh_url_without_git_suffix(self) -> None:
        owner, name, url = _parse_repo_ref("git@github.com:owner/repo")
        assert owner == "owner"
        assert name == "repo"
        assert url == "git@github.com:owner/repo.git"

    def test_invalid_ref_raises(self) -> None:
        with pytest.raises(ValidationError, match="Cannot parse repo reference"):
            _parse_repo_ref("not-a-valid-ref")


class TestResolveRepo:
    """Test resolve_repo — local path passthrough, clone, fetch, failure."""

    def test_local_path_passthrough(self, tmp_path: Path) -> None:
        path, name = resolve_repo(str(tmp_path), tmp_path / "harness")
        assert path == tmp_path
        assert name == tmp_path.name

    def test_remote_repo_triggers_clone(self, tmp_path: Path) -> None:
        harness_home = tmp_path / "harness"
        expected_dir = harness_home / "repos" / "my-app"

        with patch("action_harness.repo.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            path, name = resolve_repo("user/my-app", harness_home)

        assert path == expected_dir
        assert name == "my-app"
        # Should have called git clone
        clone_call = mock_run.call_args_list[0]
        assert "git" in clone_call.args[0]
        assert "clone" in clone_call.args[0]

    def test_already_cloned_triggers_fetch(self, tmp_path: Path) -> None:
        harness_home = tmp_path / "harness"
        repo_dir = harness_home / "repos" / "my-app"
        repo_dir.mkdir(parents=True)

        with patch("action_harness.repo.subprocess.run") as mock_run:
            # First call: git remote get-url origin (collision check)
            # Second call: git fetch origin
            mock_run.side_effect = [
                subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="https://github.com/user/my-app.git\n",
                    stderr="",
                ),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            ]
            path, name = resolve_repo("user/my-app", harness_home)

        assert path == repo_dir
        assert name == "my-app"
        # Second call should be fetch
        fetch_call = mock_run.call_args_list[1]
        assert "fetch" in fetch_call.args[0]

    def test_clone_failure_raises(self, tmp_path: Path) -> None:
        harness_home = tmp_path / "harness"

        with patch("action_harness.repo.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=128,
                stdout="",
                stderr="fatal: repository not found",
            )
            with pytest.raises(ValidationError, match="Failed to clone"):
                resolve_repo("user/nonexistent", harness_home)


class TestGetRepoDir:
    """Test _get_repo_dir — default path, collision detection, fallback."""

    def test_default_path_when_no_collision(self, tmp_path: Path) -> None:
        result = _get_repo_dir("owner", "repo", "https://github.com/owner/repo.git", tmp_path)
        assert result == tmp_path / "repos" / "repo"

    def test_same_repo_returns_same_dir(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repos" / "utils"
        repo_dir.mkdir(parents=True)

        with patch("action_harness.repo.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="https://github.com/orgA/utils.git\n",
                stderr="",
            )
            result = _get_repo_dir("orgA", "utils", "https://github.com/orgA/utils.git", tmp_path)

        assert result == repo_dir

    def test_collision_falls_back_to_owner_repo(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repos" / "utils"
        repo_dir.mkdir(parents=True)

        with patch("action_harness.repo.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="https://github.com/orgA/utils.git\n",
                stderr="",
            )
            result = _get_repo_dir("orgB", "utils", "https://github.com/orgB/utils.git", tmp_path)

        assert result == tmp_path / "repos" / "orgB-utils"
