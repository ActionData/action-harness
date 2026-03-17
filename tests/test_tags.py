"""Tests for git tag management (rollback points and shipped markers)."""

import json
import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from action_harness.cli import app
from action_harness.tags import (
    create_tag,
    get_latest_tag,
    list_tags,
    push_tag,
    tag_pre_merge,
    tag_shipped,
)

runner = CliRunner()


@pytest.fixture
def git_repo(tmp_path: Path) -> Generator[Path]:
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
    (tmp_path / "README.md").write_text("test")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    yield tmp_path


def _get_head_commit(repo: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _get_tag_commit(repo: Path, tag: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", tag],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _add_commit(repo: Path, filename: str, content: str, msg: str) -> str:
    (repo / filename).write_text(content)
    subprocess.run(["git", "add", filename], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", msg],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    return _get_head_commit(repo)


def _get_tree_hash(repo: Path, ref: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", f"{ref}^{{tree}}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _count_commits(repo: Path) -> int:
    result = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return int(result.stdout.strip())


# ── Task 1.5: Tag utility tests ─────────────────────────────────────


class TestCreateTag:
    def test_create_tag_succeeds(self, git_repo: Path) -> None:
        actual = create_tag(git_repo, "test/tag")
        assert actual == "test/tag"
        # Verify tag exists
        _get_tag_commit(git_repo, "test/tag")

    def test_create_with_collision_retries_with_timestamp(self, git_repo: Path) -> None:
        # Create the first tag
        create_tag(git_repo, "test/dup")
        # Second creation should get timestamp suffix
        actual = create_tag(git_repo, "test/dup")
        assert actual.startswith("test/dup-")
        assert len(actual) > len("test/dup-")
        # Verify both tags exist
        _get_tag_commit(git_repo, "test/dup")
        _get_tag_commit(git_repo, actual)

    def test_create_on_specific_commit(self, git_repo: Path) -> None:
        first_commit = _get_head_commit(git_repo)
        _add_commit(git_repo, "b.txt", "b", "second")
        actual = create_tag(git_repo, "test/specific", commit=first_commit)
        assert actual == "test/specific"
        assert _get_tag_commit(git_repo, actual) == first_commit


class TestPushTag:
    def test_push_success_returns_true(self, git_repo: Path) -> None:
        create_tag(git_repo, "test/push")
        with patch("action_harness.tags.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            assert push_tag(git_repo, "test/push") is True

    def test_push_failure_returns_false_and_logs_warning(
        self, git_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        create_tag(git_repo, "test/pushfail")
        # Push to non-existent remote should fail
        result = push_tag(git_repo, "test/pushfail")
        assert result is False
        captured = capsys.readouterr()
        assert "push" in captured.err.lower()

    def test_push_timeout_returns_false(self, git_repo: Path) -> None:
        create_tag(git_repo, "test/timeout")
        with patch("action_harness.tags.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=120)
            result = push_tag(git_repo, "test/timeout")
            assert result is False


class TestListTags:
    def test_list_with_3_tags_sorted_descending(self, git_repo: Path) -> None:
        # Create 3 tags with different commits, sleeping to ensure different creatordates
        create_tag(git_repo, "harness/shipped/a")
        time.sleep(1.1)  # git creatordate has second precision
        _add_commit(git_repo, "b.txt", "b", "second")
        create_tag(git_repo, "harness/shipped/b")
        time.sleep(1.1)
        _add_commit(git_repo, "c.txt", "c", "third")
        create_tag(git_repo, "harness/shipped/c")

        tags = list_tags(git_repo, "harness/shipped/*")
        assert len(tags) == 3
        # Most recent first
        assert tags[0]["label"] == "c"
        assert tags[1]["label"] == "b"
        assert tags[2]["label"] == "a"
        # Verify fields
        for t in tags:
            assert "tag" in t
            assert "commit" in t
            assert "date" in t
            assert "label" in t
            assert t["tag"].startswith("harness/shipped/")

    def test_list_empty_returns_empty_list(self, git_repo: Path) -> None:
        tags = list_tags(git_repo, "harness/shipped/*")
        assert tags == []

    def test_list_filters_by_pattern(self, git_repo: Path) -> None:
        create_tag(git_repo, "harness/shipped/x")
        create_tag(git_repo, "harness/pre-merge/y")
        shipped = list_tags(git_repo, "harness/shipped/*")
        assert len(shipped) == 1
        assert shipped[0]["label"] == "x"


class TestGetLatestTag:
    def test_get_latest_returns_most_recent(self, git_repo: Path) -> None:
        create_tag(git_repo, "harness/pre-merge/old")
        _add_commit(git_repo, "b.txt", "b", "second")
        time.sleep(0.1)
        create_tag(git_repo, "harness/pre-merge/new")
        result = get_latest_tag(git_repo, "harness/pre-merge/*")
        assert result == "harness/pre-merge/new"

    def test_get_latest_no_matches_returns_none(self, git_repo: Path) -> None:
        result = get_latest_tag(git_repo, "harness/pre-merge/*")
        assert result is None


# ── Task 2.3: Pre-merge tag tests ───────────────────────────────────


class TestTagPreMerge:
    def test_pre_merge_tag_created_on_correct_commit(self, git_repo: Path) -> None:
        # Get current branch name
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        base_branch = result.stdout.strip()

        # Create a new commit (simulating worktree being ahead)
        _add_commit(git_repo, "extra.txt", "x", "extra")

        # The tag should be on base_branch, which we pass explicitly
        # Since we're in the same repo, base_branch HEAD is the current HEAD
        # But in production, the tag is created on the base branch in the main repo
        tag_pre_merge(git_repo, "my-change", base_branch)

        # Tag should exist
        tag_commit = _get_tag_commit(git_repo, "harness/pre-merge/my-change")
        # The tag is on the base_branch HEAD (which is current HEAD after extra commit)
        assert tag_commit == _get_head_commit(git_repo)


# ── Task 3.3: Post-merge tag (tag-shipped) tests ────────────────────


class TestTagShipped:
    def test_tag_created_when_pr_merged(self, git_repo: Path) -> None:
        merge_commit = _get_head_commit(git_repo)
        mock_result = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"mergedAt": "2026-03-16T00:00:00Z", "mergeCommitSha": merge_commit}),
            stderr="",
        )
        with patch("action_harness.tags.subprocess.run") as mock_run:
            # First call is gh pr view, second is git tag, third is git push
            mock_run.side_effect = [
                mock_result,
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            ]
            result = tag_shipped(git_repo, "my-feature", "https://github.com/o/r/pull/1")
            assert result is True

    def test_no_tag_when_pr_open(self, git_repo: Path) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"mergedAt": None, "mergeCommitSha": None}),
            stderr="",
        )
        with patch("action_harness.tags.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            result = tag_shipped(git_repo, "my-feature", "https://github.com/o/r/pull/1")
            assert result is False

    def test_gh_failure_handled_gracefully(self, git_repo: Path) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="not found"
        )
        with patch("action_harness.tags.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            result = tag_shipped(git_repo, "my-feature", "https://github.com/o/r/pull/1")
            assert result is False


class TestTagShippedCli:
    def test_invalid_pr_url_exits_with_error(self, git_repo: Path) -> None:
        result = runner.invoke(
            app,
            ["tag-shipped", "--repo", str(git_repo), "--pr", "", "--label", "test"],
        )
        assert result.exit_code != 0


# ── Task 4.3: Rollback tests ────────────────────────────────────────


class TestRollback:
    def test_rollback_to_latest_tag(self, git_repo: Path) -> None:
        # Create pre-merge tag
        create_tag(git_repo, "harness/pre-merge/baseline")

        # Add more commits
        _add_commit(git_repo, "new1.txt", "x", "new1")
        _add_commit(git_repo, "new2.txt", "y", "new2")
        commits_before = _count_commits(git_repo)

        result = runner.invoke(app, ["rollback", "--repo", str(git_repo)])
        assert result.exit_code == 0

        # Exactly one new commit
        assert _count_commits(git_repo) == commits_before + 1
        # Tree matches tagged tree
        assert _get_tree_hash(git_repo, "HEAD") == _get_tree_hash(
            git_repo, "harness/pre-merge/baseline"
        )

    def test_rollback_to_specific_tag(self, git_repo: Path) -> None:
        create_tag(git_repo, "harness/pre-merge/first")
        _add_commit(git_repo, "a.txt", "a", "a")
        create_tag(git_repo, "harness/pre-merge/second")
        _add_commit(git_repo, "b.txt", "b", "b")
        commits_before = _count_commits(git_repo)

        result = runner.invoke(
            app,
            ["rollback", "--repo", str(git_repo), "--to", "harness/pre-merge/first"],
        )
        assert result.exit_code == 0
        assert _count_commits(git_repo) == commits_before + 1
        assert _get_tree_hash(git_repo, "HEAD") == _get_tree_hash(
            git_repo, "harness/pre-merge/first"
        )

    def test_no_tags_exits_with_error(self, git_repo: Path) -> None:
        result = runner.invoke(app, ["rollback", "--repo", str(git_repo)])
        assert result.exit_code != 0
        assert "No rollback points found" in result.output

    def test_dirty_working_tree_exits_with_error(self, git_repo: Path) -> None:
        create_tag(git_repo, "harness/pre-merge/test")
        (git_repo / "dirty.txt").write_text("uncommitted")
        subprocess.run(["git", "add", "dirty.txt"], cwd=git_repo, capture_output=True)

        result = runner.invoke(app, ["rollback", "--repo", str(git_repo)])
        assert result.exit_code != 0
        assert "uncommitted changes" in result.output.lower()

    def test_rollback_creates_exactly_one_commit(self, git_repo: Path) -> None:
        create_tag(git_repo, "harness/pre-merge/test")
        _add_commit(git_repo, "a.txt", "a", "a")
        _add_commit(git_repo, "b.txt", "b", "b")
        _add_commit(git_repo, "c.txt", "c", "c")
        commits_before = _count_commits(git_repo)

        runner.invoke(app, ["rollback", "--repo", str(git_repo)])

        assert _count_commits(git_repo) == commits_before + 1


# ── Task 5.3: History tests ─────────────────────────────────────────


def _stdout_lines(output: str) -> list[str]:
    """Filter CLI output to only stdout lines (exclude [tags]/[rollback] diagnostic lines)."""
    return [
        line
        for line in output.strip().splitlines()
        if line.strip() and not line.strip().startswith("[")
    ]


def _extract_json(output: str) -> str:
    """Extract JSON content from CLI output that may contain stderr diagnostic lines."""
    lines = output.splitlines()
    # Find the first line starting with '[' or '{' that looks like JSON
    json_start = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (
            stripped.startswith(("[", "{"))
            and not stripped.startswith("[tags]")
            and not stripped.startswith("[rollback]")
        ):
            json_start = i
            break
    if json_start == -1:
        return output
    return "\n".join(lines[json_start:])


class TestHistory:
    def test_history_with_3_tags_sorted_descending(self, git_repo: Path) -> None:
        create_tag(git_repo, "harness/shipped/alpha")
        time.sleep(1.1)
        _add_commit(git_repo, "b.txt", "b", "b")
        create_tag(git_repo, "harness/shipped/beta")
        time.sleep(1.1)
        _add_commit(git_repo, "c.txt", "c", "c")
        create_tag(git_repo, "harness/shipped/gamma")

        result = runner.invoke(app, ["history", "--repo", str(git_repo)])
        assert result.exit_code == 0
        lines = _stdout_lines(result.output)
        assert len(lines) == 3
        assert "gamma" in lines[0]
        assert "beta" in lines[1]
        assert "alpha" in lines[2]

    def test_history_empty_says_no_features(self, git_repo: Path) -> None:
        result = runner.invoke(app, ["history", "--repo", str(git_repo)])
        assert result.exit_code == 0
        assert "No harness-shipped features found" in result.output

    def test_history_json_output(self, git_repo: Path) -> None:
        create_tag(git_repo, "harness/shipped/x")
        time.sleep(1.1)
        _add_commit(git_repo, "b.txt", "b", "b")
        create_tag(git_repo, "harness/shipped/y")

        result = runner.invoke(app, ["history", "--repo", str(git_repo), "--json"])
        assert result.exit_code == 0
        json_text = _extract_json(result.output)
        data = json.loads(json_text)
        assert isinstance(data, list)
        assert len(data) == 2
        # Most recent first
        assert data[0]["label"] == "y"
        assert data[1]["label"] == "x"
        # Verify required keys
        for item in data:
            assert "tag" in item
            assert "commit" in item
            assert "date" in item
            assert "label" in item
