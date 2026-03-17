"""Tests for the dashboard data layer."""

import json
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

from action_harness.dashboard import (
    cross_repo_roadmap,
    list_repos,
    list_workspaces,
    read_openspec_changes,
    read_roadmap,
    repo_detail,
)


def _init_git_repo(path: Path) -> None:
    """Initialize a bare git repo at the given path."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init"],
        cwd=path,
        capture_output=True,
        timeout=120,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=path,
        capture_output=True,
        timeout=120,
    )


def _init_workspace(path: Path, branch: str = "harness/test") -> None:
    """Initialize a workspace dir as a git repo with a commit."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-b", branch],
        cwd=path,
        capture_output=True,
        timeout=120,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=path,
        capture_output=True,
        timeout=120,
    )


# ── 5.1: list_repos with 2 repos ─────────────────────────────────────


def test_list_repos_two_repos(tmp_path: Path) -> None:
    """5.1: list_repos with 2 repo dirs, one with HARNESS.md."""
    harness_home = tmp_path
    repos_dir = harness_home / "repos"

    # Repo 1: has HARNESS.md, has workspace, has openspec change
    repo1 = repos_dir / "repo1"
    _init_git_repo(repo1)
    (repo1 / "HARNESS.md").write_text("# Test")
    changes_dir = repo1 / "openspec" / "changes" / "active1"
    changes_dir.mkdir(parents=True)
    (changes_dir / "tasks.md").write_text("- [x] done\n- [ ] todo\n")

    # Create workspace for repo1
    ws = harness_home / "workspaces" / "repo1" / "change1"
    _init_workspace(ws)

    # Repo 2: no HARNESS.md
    repo2 = repos_dir / "repo2"
    _init_git_repo(repo2)

    summaries = list_repos(harness_home)
    assert len(summaries) == 2

    s1 = next(s for s in summaries if s.name == "repo1")
    s2 = next(s for s in summaries if s.name == "repo2")

    assert s1.has_harness_md is True
    assert s2.has_harness_md is False
    assert s1.workspace_count == 1
    assert s1.active_changes == 1


# ── 5.2: list_repos skips non-git dirs ───────────────────────────────


def test_list_repos_skips_non_git(tmp_path: Path) -> None:
    """5.2: Non-git directories are excluded."""
    harness_home = tmp_path
    repos_dir = harness_home / "repos"

    # Git repo
    _init_git_repo(repos_dir / "real-repo")
    # Plain directory (not git)
    (repos_dir / "not-a-repo").mkdir(parents=True)

    summaries = list_repos(harness_home)
    assert len(summaries) == 1
    assert summaries[0].name == "real-repo"


# ── 5.3: repo_detail reads HARNESS.md ────────────────────────────────


def test_repo_detail_harness_md(tmp_path: Path) -> None:
    """5.3: repo_detail reads HARNESS.md content."""
    harness_home = tmp_path
    repo = harness_home / "repos" / "test-repo"
    _init_git_repo(repo)

    content = "line 1\nline 2\nline 3\nline 4\nline 5\n"
    (repo / "HARNESS.md").write_text(content)

    detail = repo_detail(harness_home, "test-repo")
    assert detail.harness_md_content == content


# ── 5.4: repo_detail reads protected patterns ────────────────────────


def test_repo_detail_protected_patterns(tmp_path: Path) -> None:
    """5.4: repo_detail reads protected-paths.yml."""
    harness_home = tmp_path
    repo = harness_home / "repos" / "test-repo"
    _init_git_repo(repo)

    harness_dir = repo / ".harness"
    harness_dir.mkdir()
    (harness_dir / "protected-paths.yml").write_text('protected: ["src/core/**", "*.toml"]\n')

    detail = repo_detail(harness_home, "test-repo")
    assert detail.protected_patterns == ["src/core/**", "*.toml"]


# ── 5.5: read_openspec_changes with tasks ────────────────────────────


def test_read_openspec_changes_with_tasks(tmp_path: Path) -> None:
    """5.5: Count tasks correctly and count archived changes."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Active change with 3 done, 2 todo
    change_dir = repo / "openspec" / "changes" / "my-change"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text(
        "- [x] task 1\n- [x] task 2\n- [x] task 3\n- [ ] task 4\n- [ ] task 5\n"
    )

    # Archived changes
    archive = repo / "openspec" / "changes" / "archive"
    (archive / "old1").mkdir(parents=True)
    (archive / "old2").mkdir(parents=True)

    changes, completed_count = read_openspec_changes(repo)
    assert len(changes) == 1
    assert changes[0].task_count == 5
    assert changes[0].tasks_complete == 3
    assert changes[0].progress_pct == 60.0
    assert completed_count == 2


# ── 5.6: read_openspec_changes with no openspec dir ──────────────────


def test_read_openspec_changes_no_dir(tmp_path: Path) -> None:
    """5.6: No openspec dir returns empty."""
    changes, completed_count = read_openspec_changes(tmp_path)
    assert changes == []
    assert completed_count == 0


# ── 5.7: read_roadmap ────────────────────────────────────────────────


def test_read_roadmap_exists(tmp_path: Path) -> None:
    """5.7: read_roadmap returns file content when it exists."""
    roadmap_dir = tmp_path / "openspec"
    roadmap_dir.mkdir()
    content = "# Roadmap\n\n- Item 1\n"
    (roadmap_dir / "ROADMAP.md").write_text(content)

    result = read_roadmap(tmp_path)
    assert result == content


def test_read_roadmap_missing(tmp_path: Path) -> None:
    """5.7: read_roadmap returns None when file missing."""
    result = read_roadmap(tmp_path)
    assert result is None


# ── 5.8: cross_repo_roadmap ──────────────────────────────────────────


def test_cross_repo_roadmap(tmp_path: Path) -> None:
    """5.8: Cross-repo roadmap with 2 repos."""
    harness_home = tmp_path
    repos_dir = harness_home / "repos"

    # Repo 1: has OpenSpec
    repo1 = repos_dir / "repo1"
    _init_git_repo(repo1)
    roadmap_dir = repo1 / "openspec"
    roadmap_dir.mkdir()
    (roadmap_dir / "ROADMAP.md").write_text("# Roadmap for repo1\n")
    change_dir = roadmap_dir / "changes" / "feat1"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [x] done\n- [ ] todo\n")

    # Repo 2: no OpenSpec
    repo2 = repos_dir / "repo2"
    _init_git_repo(repo2)

    roadmaps = cross_repo_roadmap(harness_home)
    assert len(roadmaps) == 2

    rm1 = next(r for r in roadmaps if r.repo_name == "repo1")
    rm2 = next(r for r in roadmaps if r.repo_name == "repo2")

    assert rm1.roadmap_content is not None
    assert len(rm1.active_changes) == 1
    assert rm2.roadmap_content is None
    assert rm2.active_changes == []


# ── 5.9: workspace staleness ─────────────────────────────────────────


def test_workspace_stale(tmp_path: Path) -> None:
    """5.9: Workspace is stale when >7 days old and no open PR."""
    harness_home = tmp_path
    ws_path = harness_home / "workspaces" / "repo1" / "old-change"
    _init_workspace(ws_path, branch="harness/old-change")

    # Mock git log to return timestamp 10 days ago
    old_ts = str(int(time.time()) - 10 * 86400)

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "log" in cmd and "--format=%ct" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=old_ts + "\n", stderr="")
        if "rev-parse" in cmd and "--abbrev-ref" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="harness/old-change\n", stderr="")
        if "gh" in cmd[0] if cmd else False:
            # gh pr list returns empty list
            return subprocess.CompletedProcess(cmd, 0, stdout="[]\n", stderr="")
        return subprocess.run(cmd, **kwargs)  # type: ignore[arg-type]

    with patch("action_harness.dashboard.subprocess.run", side_effect=mock_run):
        workspaces = list_workspaces(harness_home)

    assert len(workspaces) == 1
    assert workspaces[0].stale is True


# ── 5.10: workspace not stale with open PR ───────────────────────────


def test_workspace_not_stale_with_pr(tmp_path: Path) -> None:
    """5.10: Workspace not stale when open PR exists despite old commits."""
    harness_home = tmp_path
    ws_path = harness_home / "workspaces" / "repo1" / "old-change"
    _init_workspace(ws_path, branch="harness/old-change")

    old_ts = str(int(time.time()) - 10 * 86400)

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "log" in cmd and "--format=%ct" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=old_ts + "\n", stderr="")
        if "rev-parse" in cmd and "--abbrev-ref" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="harness/old-change\n", stderr="")
        if cmd and cmd[0] == "gh":
            pr_json = json.dumps([{"number": 42}])
            return subprocess.CompletedProcess(cmd, 0, stdout=pr_json + "\n", stderr="")
        return subprocess.run(cmd, **kwargs)  # type: ignore[arg-type]

    with patch("action_harness.dashboard.subprocess.run", side_effect=mock_run):
        workspaces = list_workspaces(harness_home)

    assert len(workspaces) == 1
    assert workspaces[0].stale is False
    assert workspaces[0].has_open_pr is True


# ── 5.11: list_repos with empty repos/ dir ───────────────────────────


def test_list_repos_empty(tmp_path: Path) -> None:
    """5.11: Empty repos/ dir returns empty list."""
    harness_home = tmp_path
    (harness_home / "repos").mkdir()

    summaries = list_repos(harness_home)
    assert summaries == []
