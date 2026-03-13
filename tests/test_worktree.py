"""Tests for git worktree management."""

import subprocess
from pathlib import Path

import pytest

from action_harness.worktree import cleanup_worktree, create_worktree


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a real git repo with an initial commit."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    # Create initial commit so we have a branch to base worktrees on
    (tmp_path / "README.md").write_text("test")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    return tmp_path


class TestCreateWorktree:
    def test_creates_worktree_and_branch(self, git_repo: Path) -> None:
        result = create_worktree("test-change", git_repo)

        assert result.success is True
        assert result.stage == "worktree"
        assert result.branch == "harness/test-change"
        assert result.worktree_path is not None
        assert result.worktree_path.exists()
        assert result.error is None

        # Verify the branch exists
        check = subprocess.run(
            ["git", "rev-parse", "--verify", "harness/test-change"],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        assert check.returncode == 0

    def test_branch_already_exists_reruns_cleanly(self, git_repo: Path) -> None:
        # First run
        result1 = create_worktree("test-change", git_repo)
        assert result1.success is True
        old_path = result1.worktree_path

        # Second run — should clean up old worktree and create fresh
        result2 = create_worktree("test-change", git_repo)
        assert result2.success is True
        assert result2.worktree_path is not None
        assert result2.worktree_path != old_path

        # Old worktree should be gone
        assert old_path is not None
        assert not old_path.exists()

    def test_worktree_is_on_correct_branch(self, git_repo: Path) -> None:
        result = create_worktree("my-feature", git_repo)
        assert result.success is True
        assert result.worktree_path is not None

        check = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=result.worktree_path,
            capture_output=True,
            text=True,
        )
        assert check.stdout.strip() == "harness/my-feature"

    def test_returns_result_object(self, git_repo: Path) -> None:
        result = create_worktree("test-change", git_repo)
        from action_harness.models import WorktreeResult

        assert isinstance(result, WorktreeResult)


class TestCleanupWorktree:
    def test_cleanup_removes_worktree(self, git_repo: Path) -> None:
        result = create_worktree("cleanup-test", git_repo)
        assert result.success is True
        assert result.worktree_path is not None
        assert result.worktree_path.exists()

        cleanup_worktree(git_repo, result.worktree_path, result.branch)

        assert not result.worktree_path.exists()

    def test_cleanup_preserves_branch_by_default(self, git_repo: Path) -> None:
        result = create_worktree("preserve-test", git_repo)
        assert result.success is True
        assert result.worktree_path is not None

        cleanup_worktree(git_repo, result.worktree_path, result.branch)

        # Branch should still exist
        check = subprocess.run(
            ["git", "rev-parse", "--verify", "harness/preserve-test"],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        assert check.returncode == 0

    def test_cleanup_can_delete_branch(self, git_repo: Path) -> None:
        result = create_worktree("delete-test", git_repo)
        assert result.success is True
        assert result.worktree_path is not None

        cleanup_worktree(
            git_repo,
            result.worktree_path,
            result.branch,
            preserve_branch=False,
        )

        # Branch should be gone
        check = subprocess.run(
            ["git", "rev-parse", "--verify", "harness/delete-test"],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        assert check.returncode != 0
