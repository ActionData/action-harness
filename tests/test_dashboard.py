"""Tests for the dashboard data layer."""

import json
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest

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
    """5.1: list_repos with 2 project dirs, one with HARNESS.md."""
    harness_home = tmp_path

    # Project 1: has HARNESS.md, has workspace, has openspec change
    project1 = harness_home / "projects" / "repo1"
    repo1 = project1 / "repo"
    _init_git_repo(repo1)
    (repo1 / "HARNESS.md").write_text("# Test")
    (project1 / "config.yaml").write_text("repo_name: repo1\nremote_url: null\n")
    changes_dir = repo1 / "openspec" / "changes" / "active1"
    changes_dir.mkdir(parents=True)
    (changes_dir / "tasks.md").write_text("- [x] done\n- [ ] todo\n")

    # Create workspace for repo1
    ws = project1 / "workspaces" / "change1"
    _init_workspace(ws)

    # Project 2: no HARNESS.md
    project2 = harness_home / "projects" / "repo2"
    repo2 = project2 / "repo"
    _init_git_repo(repo2)
    (project2 / "config.yaml").write_text("repo_name: repo2\nremote_url: null\n")

    summaries = list_repos(harness_home)
    assert len(summaries) == 2

    s1 = next(s for s in summaries if s.name == "repo1")
    s2 = next(s for s in summaries if s.name == "repo2")

    assert s1.has_harness_md is True
    assert s2.has_harness_md is False
    assert s1.workspace_count == 1
    assert s1.active_changes == 1


# ── 5.2: list_repos skips non-git dirs ───────────────────────────────


def test_list_repos_skips_no_config(tmp_path: Path) -> None:
    """5.2: Projects without config.yaml are excluded."""
    harness_home = tmp_path

    # Project with config.yaml
    project1 = harness_home / "projects" / "real-repo"
    _init_git_repo(project1 / "repo")
    (project1 / "config.yaml").write_text("repo_name: real-repo\nremote_url: null\n")

    # Project without config.yaml
    project2 = harness_home / "projects" / "not-managed"
    _init_git_repo(project2 / "repo")

    summaries = list_repos(harness_home)
    assert len(summaries) == 1
    assert summaries[0].name == "real-repo"


# ── 5.3: repo_detail reads HARNESS.md ────────────────────────────────


def test_repo_detail_harness_md(tmp_path: Path) -> None:
    """5.3: repo_detail reads HARNESS.md content."""
    harness_home = tmp_path
    project = harness_home / "projects" / "test-repo"
    repo = project / "repo"
    _init_git_repo(repo)
    (project / "config.yaml").write_text("repo_name: test-repo\nremote_url: null\n")

    content = "line 1\nline 2\nline 3\nline 4\nline 5\n"
    (repo / "HARNESS.md").write_text(content)

    detail = repo_detail(harness_home, "test-repo")
    assert detail.harness_md_content == content


# ── 5.4: repo_detail reads protected patterns ────────────────────────


def test_repo_detail_protected_patterns(tmp_path: Path) -> None:
    """5.4: repo_detail reads protected-paths.yml."""
    harness_home = tmp_path
    project = harness_home / "projects" / "test-repo"
    repo = project / "repo"
    _init_git_repo(repo)
    (project / "config.yaml").write_text("repo_name: test-repo\nremote_url: null\n")

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
    """5.8: Cross-repo roadmap with 2 projects."""
    harness_home = tmp_path

    # Project 1: has OpenSpec
    project1 = harness_home / "projects" / "repo1"
    repo1 = project1 / "repo"
    _init_git_repo(repo1)
    (project1 / "config.yaml").write_text("repo_name: repo1\nremote_url: null\n")
    roadmap_dir = repo1 / "openspec"
    roadmap_dir.mkdir()
    (roadmap_dir / "ROADMAP.md").write_text("# Roadmap for repo1\n")
    change_dir = roadmap_dir / "changes" / "feat1"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [x] done\n- [ ] todo\n")

    # Project 2: no OpenSpec
    project2 = harness_home / "projects" / "repo2"
    repo2 = project2 / "repo"
    _init_git_repo(repo2)
    (project2 / "config.yaml").write_text("repo_name: repo2\nremote_url: null\n")

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
    ws_path = harness_home / "projects" / "repo1" / "workspaces" / "old-change"
    _init_workspace(ws_path, branch="harness/old-change")

    # Mock git log to return timestamp 10 days ago
    old_ts = str(int(time.time()) - 10 * 86400)

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "log" in cmd and "--format=%ct" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=old_ts + "\n", stderr="")
        if "rev-parse" in cmd and "--abbrev-ref" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="harness/old-change\n", stderr="")
        if cmd and cmd[0] == "gh":
            # gh pr list returns empty list
            return subprocess.CompletedProcess(cmd, 0, stdout="[]\n", stderr="")
        raise ValueError(f"Unexpected subprocess call: {cmd}")

    with patch("action_harness.dashboard.subprocess.run", side_effect=mock_run):
        workspaces = list_workspaces(harness_home)

    assert len(workspaces) == 1
    assert workspaces[0].stale is True


# ── 5.10: workspace not stale with open PR ───────────────────────────


def test_workspace_not_stale_with_pr(tmp_path: Path) -> None:
    """5.10: Workspace not stale when open PR exists despite old commits."""
    harness_home = tmp_path
    ws_path = harness_home / "projects" / "repo1" / "workspaces" / "old-change"
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
        raise ValueError(f"Unexpected subprocess call: {cmd}")

    with patch("action_harness.dashboard.subprocess.run", side_effect=mock_run):
        workspaces = list_workspaces(harness_home)

    assert len(workspaces) == 1
    assert workspaces[0].stale is False
    assert workspaces[0].has_open_pr is True


# ── 5.11: list_repos with empty repos/ dir ───────────────────────────


def test_list_repos_empty(tmp_path: Path) -> None:
    """5.11: Empty projects/ dir returns empty list."""
    harness_home = tmp_path
    (harness_home / "projects").mkdir()

    summaries = list_repos(harness_home)
    assert summaries == []


# ── Edge cases (from review findings) ────────────────────────────────


def test_repo_detail_not_found(tmp_path: Path) -> None:
    """repo_detail raises FileNotFoundError for missing repo."""
    harness_home = tmp_path
    (harness_home / "projects").mkdir()

    with pytest.raises(FileNotFoundError, match="not found"):
        repo_detail(harness_home, "nonexistent")


def test_list_workspaces_skips_non_git(tmp_path: Path) -> None:
    """list_workspaces skips non-git workspace directories."""
    harness_home = tmp_path
    # Create a workspace dir without .git
    plain_dir = harness_home / "projects" / "repo1" / "workspaces" / "not-a-worktree"
    plain_dir.mkdir(parents=True)

    workspaces = list_workspaces(harness_home)
    assert workspaces == []


def test_read_openspec_changes_unreadable_tasks(tmp_path: Path) -> None:
    """read_openspec_changes handles unreadable tasks.md gracefully."""
    change_dir = tmp_path / "openspec" / "changes" / "broken-change"
    change_dir.mkdir(parents=True)
    tasks = change_dir / "tasks.md"
    tasks.write_text("- [x] done\n- [ ] todo\n")

    # Make tasks.md a directory to force OSError on read
    tasks.unlink()
    tasks.mkdir()

    changes, completed = read_openspec_changes(tmp_path)
    assert len(changes) == 1
    assert changes[0].task_count == 0
    assert changes[0].tasks_complete == 0


# ── CLI smoke tests ──────────────────────────────────────────────────


def test_cli_repos_json(tmp_path: Path) -> None:
    """CLI repos --json returns valid JSON array."""
    from typer.testing import CliRunner

    from action_harness.cli import app

    runner = CliRunner()
    project = tmp_path / "projects" / "test-repo"
    repo = project / "repo"
    _init_git_repo(repo)
    (project / "config.yaml").write_text("repo_name: test-repo\nremote_url: null\n")

    result = runner.invoke(app, ["repos", "--json", "--harness-home", str(tmp_path)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "test-repo"


def test_cli_repos_formatted(tmp_path: Path) -> None:
    """CLI repos formatted output contains repo name and markers."""
    from typer.testing import CliRunner

    from action_harness.cli import app

    runner = CliRunner()
    project = tmp_path / "projects" / "my-repo"
    repo = project / "repo"
    _init_git_repo(repo)
    (project / "config.yaml").write_text("repo_name: my-repo\nremote_url: null\n")

    result = runner.invoke(app, ["repos", "--harness-home", str(tmp_path)])
    assert result.exit_code == 0
    assert "my-repo" in result.stdout
    assert "HARNESS.md:" in result.stdout
    assert "✗" in result.stdout


def test_cli_repos_show_json(tmp_path: Path) -> None:
    """CLI repos show --json returns valid JSON."""
    from typer.testing import CliRunner

    from action_harness.cli import app

    runner = CliRunner()
    project = tmp_path / "projects" / "test-repo"
    repo = project / "repo"
    _init_git_repo(repo)
    (project / "config.yaml").write_text("repo_name: test-repo\nremote_url: null\n")
    (repo / "HARNESS.md").write_text("# Config\n")

    result = runner.invoke(
        app, ["repos", "show", "test-repo", "--json", "--harness-home", str(tmp_path)]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["summary"]["name"] == "test-repo"
    assert data["harness_md_content"] == "# Config\n"


def test_cli_repos_show_not_found(tmp_path: Path) -> None:
    """CLI repos show exits with error for missing repo."""
    from typer.testing import CliRunner

    from action_harness.cli import app

    runner = CliRunner()
    (tmp_path / "projects").mkdir()

    result = runner.invoke(app, ["repos", "show", "nope", "--harness-home", str(tmp_path)])
    assert result.exit_code == 1


def test_cli_repos_show_formatted(tmp_path: Path) -> None:
    """CLI repos show formatted output has section headers."""
    from typer.testing import CliRunner

    from action_harness.cli import app

    runner = CliRunner()
    project = tmp_path / "projects" / "test-repo"
    repo = project / "repo"
    _init_git_repo(repo)
    (project / "config.yaml").write_text("repo_name: test-repo\nremote_url: null\n")

    result = runner.invoke(app, ["repos", "show", "test-repo", "--harness-home", str(tmp_path)])
    assert result.exit_code == 0
    assert "HARNESS.md" in result.stdout
    assert "Protected Patterns" in result.stdout
    assert "Workspaces" in result.stdout
    assert "Roadmap" in result.stdout
    assert "OpenSpec Changes" in result.stdout


def test_cli_workspaces_json(tmp_path: Path) -> None:
    """CLI workspaces --json returns valid JSON array."""
    from typer.testing import CliRunner

    from action_harness.cli import app

    runner = CliRunner()
    # Empty workspaces
    result = runner.invoke(app, ["workspaces", "--json", "--harness-home", str(tmp_path)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data == []


def test_cli_workspaces_formatted_empty(tmp_path: Path) -> None:
    """CLI workspaces formatted shows 'No workspaces found.' when empty."""
    from typer.testing import CliRunner

    from action_harness.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["workspaces", "--harness-home", str(tmp_path)])
    assert result.exit_code == 0
    assert "No workspaces found." in result.stdout


def test_cli_roadmap_json(tmp_path: Path) -> None:
    """CLI roadmap --json returns valid JSON array."""
    from typer.testing import CliRunner

    from action_harness.cli import app

    runner = CliRunner()
    project = tmp_path / "projects" / "test-repo"
    repo = project / "repo"
    _init_git_repo(repo)
    (project / "config.yaml").write_text("repo_name: test-repo\nremote_url: null\n")

    result = runner.invoke(app, ["roadmap", "--json", "--harness-home", str(tmp_path)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["repo_name"] == "test-repo"


def test_cli_roadmap_formatted(tmp_path: Path) -> None:
    """CLI roadmap formatted shows repo names and No OpenSpec indicator."""
    from typer.testing import CliRunner

    from action_harness.cli import app

    runner = CliRunner()
    project = tmp_path / "projects" / "test-repo"
    repo = project / "repo"
    _init_git_repo(repo)
    (project / "config.yaml").write_text("repo_name: test-repo\nremote_url: null\n")

    result = runner.invoke(app, ["roadmap", "--harness-home", str(tmp_path)])
    assert result.exit_code == 0
    assert "test-repo" in result.stdout
    assert "No OpenSpec" in result.stdout


def test_cli_roadmap_with_progress(tmp_path: Path) -> None:
    """CLI roadmap shows progress bars for active changes."""
    from typer.testing import CliRunner

    from action_harness.cli import app

    runner = CliRunner()
    project = tmp_path / "projects" / "test-repo"
    repo = project / "repo"
    _init_git_repo(repo)
    (project / "config.yaml").write_text("repo_name: test-repo\nremote_url: null\n")
    change_dir = repo / "openspec" / "changes" / "my-feature"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [x] done\n- [ ] todo\n")

    result = runner.invoke(app, ["roadmap", "--harness-home", str(tmp_path)])
    assert result.exit_code == 0
    assert "◉" in result.stdout
    assert "█" in result.stdout
    assert "50%" in result.stdout


def test_progress_bar_bounds() -> None:
    """_progress_bar clamps values outside [0, 100]."""
    from action_harness.cli import _progress_bar

    bar_over = _progress_bar(150.0)
    assert bar_over == "[████████████████████]"

    bar_under = _progress_bar(-10.0)
    assert bar_under == "[░░░░░░░░░░░░░░░░░░░░]"

    bar_zero = _progress_bar(0.0)
    assert bar_zero == "[░░░░░░░░░░░░░░░░░░░░]"

    bar_full = _progress_bar(100.0)
    assert bar_full == "[████████████████████]"
