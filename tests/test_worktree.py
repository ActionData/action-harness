"""Tests for git worktree management."""

import shutil
import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest

from action_harness.worktree import cleanup_worktree, create_worktree


@pytest.fixture
def git_repo(tmp_path: Path) -> Generator[Path]:
    """Create a real git repo with an initial commit.

    Cleans up any worktrees created in /tmp/action-harness-* after the test.
    """
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

    yield tmp_path

    # Teardown: remove all worktrees registered with this repo
    list_result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    for line in list_result.stdout.splitlines():
        if line.startswith("worktree "):
            wt_path = Path(line.split(" ", 1)[1])
            if wt_path != tmp_path:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(wt_path)],
                    cwd=tmp_path,
                    capture_output=True,
                )
                # Clean up parent temp directory
                parent = wt_path.parent
                if parent.name.startswith("action-harness-") and parent.exists():
                    shutil.rmtree(parent, ignore_errors=True)


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

    def test_failure_returns_error_result(self, tmp_path: Path) -> None:
        """create_worktree on a non-git directory returns failure result."""
        # tmp_path is not a git repo, so git worktree add will fail
        # Need to at least make it look like a git repo for _cleanup to not crash
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        # No commits — base branch doesn't exist, so worktree add fails
        result = create_worktree("test-change", tmp_path)
        assert result.success is False
        assert result.error is not None
        assert "Failed to create worktree" in result.error
        assert result.worktree_path is None


class TestCleanupWorktree:
    def test_cleanup_removes_worktree(self, git_repo: Path) -> None:
        result = create_worktree("cleanup-test", git_repo)
        assert result.success is True
        assert result.worktree_path is not None
        assert result.worktree_path.exists()

        cleanup_result = cleanup_worktree(git_repo, result.worktree_path, result.branch)

        assert not result.worktree_path.exists()
        assert cleanup_result.success is True

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
