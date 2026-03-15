"""Tests for repository management module."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from action_harness.cli import ValidationError
from action_harness.repo import (
    _clone_or_fetch,
    _detect_gh_protocol,
    _get_repo_dir,
    _normalize_github_identity,
    _parse_repo_ref,
    resolve_repo,
)


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

        with (
            patch("action_harness.repo._detect_gh_protocol", return_value="https"),
            patch("action_harness.repo.subprocess.run") as mock_run,
        ):
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

        with (
            patch("action_harness.repo._detect_gh_protocol", return_value="https"),
            patch("action_harness.repo.subprocess.run") as mock_run,
        ):
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

        with (
            patch("action_harness.repo._detect_gh_protocol", return_value="https"),
            patch("action_harness.repo.subprocess.run") as mock_run,
        ):
            # HTTPS clone fails, SSH fallback also fails
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

    def test_same_repo_https_existing_ssh_clone_url(self, tmp_path: Path) -> None:
        """Existing remote is HTTPS, clone_url is SSH — same repo, no collision."""
        repo_dir = tmp_path / "repos" / "utils"
        repo_dir.mkdir(parents=True)

        with patch("action_harness.repo.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="https://github.com/orgA/utils.git\n",
                stderr="",
            )
            result = _get_repo_dir("orgA", "utils", "git@github.com:orgA/utils.git", tmp_path)

        assert result == repo_dir

    def test_same_repo_ssh_existing_https_clone_url(self, tmp_path: Path) -> None:
        """Existing remote is SSH, clone_url is HTTPS — same repo, no collision."""
        repo_dir = tmp_path / "repos" / "utils"
        repo_dir.mkdir(parents=True)

        with patch("action_harness.repo.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="git@github.com:orgA/utils.git\n",
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


class TestNormalizeGithubIdentity:
    """Test _normalize_github_identity — extract owner/repo from any GitHub URL."""

    def test_https_url(self) -> None:
        assert _normalize_github_identity("https://github.com/owner/repo.git") == "owner/repo"

    def test_https_url_without_git_suffix(self) -> None:
        assert _normalize_github_identity("https://github.com/owner/repo") == "owner/repo"

    def test_https_url_with_trailing_slash(self) -> None:
        assert _normalize_github_identity("https://github.com/owner/repo/") == "owner/repo"

    def test_ssh_url(self) -> None:
        assert _normalize_github_identity("git@github.com:owner/repo.git") == "owner/repo"

    def test_ssh_url_without_git_suffix(self) -> None:
        assert _normalize_github_identity("git@github.com:owner/repo") == "owner/repo"

    def test_non_github_url_returns_none(self) -> None:
        assert _normalize_github_identity("https://gitlab.com/owner/repo.git") is None

    def test_invalid_url_returns_none(self) -> None:
        assert _normalize_github_identity("not-a-url") is None


class TestDetectGhProtocol:
    """Test _detect_gh_protocol — gh auth token exit codes and missing gh."""

    def test_gh_token_success_returns_https(self) -> None:
        with patch("action_harness.repo.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="gho_xxxx\n", stderr=""
            )
            assert _detect_gh_protocol() == "https"
            mock_run.assert_called_once_with(
                ["gh", "auth", "token"], capture_output=True, text=True
            )

    def test_gh_token_failure_returns_ssh(self) -> None:
        with patch("action_harness.repo.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="not logged in"
            )
            assert _detect_gh_protocol() == "ssh"

    def test_gh_not_available_returns_https(self) -> None:
        with patch("action_harness.repo.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("gh not found")
            assert _detect_gh_protocol() == "https"


class TestResolveRepoProtocolDetection:
    """Test resolve_repo protocol detection for shorthand inputs."""

    def test_shorthand_ssh_detection_uses_ssh_url(self, tmp_path: Path) -> None:
        harness_home = tmp_path / "harness"

        with (
            patch("action_harness.repo._detect_gh_protocol", return_value="ssh") as mock_detect,
            patch("action_harness.repo.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            path, name = resolve_repo("user/my-app", harness_home)

        mock_detect.assert_called_once()
        # Clone should use SSH URL
        clone_call = mock_run.call_args_list[0]
        assert "git@github.com:user/my-app.git" in clone_call.args[0]

    def test_shorthand_https_detection_uses_https_url(self, tmp_path: Path) -> None:
        harness_home = tmp_path / "harness"

        with (
            patch("action_harness.repo._detect_gh_protocol", return_value="https") as mock_detect,
            patch("action_harness.repo.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            path, name = resolve_repo("user/my-app", harness_home)

        mock_detect.assert_called_once()
        # Clone should use HTTPS URL
        clone_call = mock_run.call_args_list[0]
        assert "https://github.com/user/my-app.git" in clone_call.args[0]

    def test_parse_repo_ref_not_mocked_still_returns_https(self) -> None:
        """_parse_repo_ref always returns HTTPS for shorthand — swap happens in resolve_repo."""
        owner, name, url = _parse_repo_ref("user/repo")
        assert url == "https://github.com/user/repo.git"


class TestCloneFallback:
    """Test SSH fallback when HTTPS clone fails."""

    def test_https_fails_ssh_succeeds(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"

        with patch("action_harness.repo.subprocess.run") as mock_run:
            mock_run.side_effect = [
                # HTTPS clone fails
                subprocess.CompletedProcess(
                    args=[], returncode=128, stdout="", stderr="could not read Username"
                ),
                # SSH clone succeeds
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                # git remote set-url origin
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            ]
            _clone_or_fetch("https://github.com/user/repo.git", repo_dir, verbose=False)

        # Verify SSH clone was attempted
        ssh_clone_call = mock_run.call_args_list[1]
        assert "git@github.com:user/repo.git" in ssh_clone_call.args[0]
        # Verify remote URL was updated
        set_url_call = mock_run.call_args_list[2]
        assert "set-url" in set_url_call.args[0]
        assert "git@github.com:user/repo.git" in set_url_call.args[0]

    def test_both_protocols_fail_raises_with_both_errors(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"

        with patch("action_harness.repo.subprocess.run") as mock_run:
            mock_run.side_effect = [
                # HTTPS clone fails
                subprocess.CompletedProcess(
                    args=[], returncode=128, stdout="", stderr="HTTPS error"
                ),
                # SSH clone also fails
                subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="SSH error"),
            ]
            with pytest.raises(ValidationError, match="HTTPS.*SSH"):
                _clone_or_fetch("https://github.com/user/repo.git", repo_dir, verbose=False)

    def test_ssh_url_no_fallback(self, tmp_path: Path) -> None:
        """SSH URLs that fail don't trigger fallback."""
        repo_dir = tmp_path / "repo"

        with patch("action_harness.repo.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr="Permission denied"
            )
            with pytest.raises(ValidationError, match="Failed to clone"):
                _clone_or_fetch("git@github.com:user/repo.git", repo_dir, verbose=False)

        # Only one call — no fallback attempt
        assert mock_run.call_count == 1


class TestExplicitUrlBypassDetection:
    """Test that explicit URLs bypass protocol detection but fallback still applies."""

    def test_explicit_ssh_url_skips_detection(self, tmp_path: Path) -> None:
        harness_home = tmp_path / "harness"

        with (
            patch("action_harness.repo._detect_gh_protocol") as mock_detect,
            patch("action_harness.repo.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            resolve_repo("git@github.com:user/repo.git", harness_home)

        mock_detect.assert_not_called()

    def test_explicit_https_url_skips_detection(self, tmp_path: Path) -> None:
        harness_home = tmp_path / "harness"

        with (
            patch("action_harness.repo._detect_gh_protocol") as mock_detect,
            patch("action_harness.repo.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            resolve_repo("https://github.com/user/repo.git", harness_home)

        mock_detect.assert_not_called()

    def test_explicit_https_url_fallback_on_failure(self, tmp_path: Path) -> None:
        harness_home = tmp_path / "harness"

        with (
            patch("action_harness.repo._detect_gh_protocol") as mock_detect,
            patch("action_harness.repo.subprocess.run") as mock_run,
        ):
            mock_run.side_effect = [
                # HTTPS clone fails
                subprocess.CompletedProcess(
                    args=[], returncode=128, stdout="", stderr="auth failed"
                ),
                # SSH fallback succeeds
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                # git remote set-url
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            ]
            resolve_repo("https://github.com/user/repo.git", harness_home)

        # Detection was NOT called (explicit URL)
        mock_detect.assert_not_called()
        # But SSH fallback was attempted
        ssh_clone_call = mock_run.call_args_list[1]
        assert "git@github.com:user/repo.git" in ssh_clone_call.args[0]
