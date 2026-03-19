"""Tests for project consolidation — unified projects/<name>/ directory layout."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import yaml

from action_harness.dashboard import list_repos
from action_harness.repo import ensure_project_dir, write_project_config
from action_harness.reporting import load_manifests


def _init_git_repo(path: Path) -> None:
    """Initialize a git repo at the given path."""
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


def _make_manifest_json(
    change_name: str = "test-change",
    success: bool = True,
    started_at: str = "2026-03-16T10:00:00+00:00",
) -> str:
    """Create minimal RunManifest JSON for testing."""
    return json.dumps(
        {
            "change_name": change_name,
            "repo_path": "/tmp/repo",
            "started_at": started_at,
            "completed_at": "2026-03-16T10:02:00+00:00",
            "success": success,
            "stages": [
                {
                    "stage": "worktree",
                    "success": True,
                    "worktree_path": "/tmp/wt",
                }
            ],
            "total_duration_seconds": 120.0,
            "total_cost_usd": 1.50,
        }
    )


# ── 9.1: Test ensure_project_dir ────────────────────────────────────


def test_ensure_project_dir(tmp_path: Path) -> None:
    """9.1: ensure_project_dir creates project structure."""
    project_dir = ensure_project_dir(tmp_path, "test-app")

    assert project_dir == tmp_path / "projects" / "test-app"
    assert (project_dir / "repo").is_dir()
    assert (project_dir / "workspaces").is_dir()
    assert (project_dir / "runs").is_dir()
    assert (project_dir / "knowledge").is_dir()
    # config.yaml should NOT be created by ensure_project_dir
    assert not (project_dir / "config.yaml").exists()


def test_ensure_project_dir_idempotent(tmp_path: Path) -> None:
    """ensure_project_dir is idempotent — calling twice doesn't error."""
    project_dir1 = ensure_project_dir(tmp_path, "test-app")
    project_dir2 = ensure_project_dir(tmp_path, "test-app")
    assert project_dir1 == project_dir2
    assert (project_dir1 / "repo").is_dir()


# ── 9.2: Test write_project_config ──────────────────────────────────


def test_write_project_config(tmp_path: Path) -> None:
    """9.2: write_project_config creates config.yaml with correct fields."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    write_project_config(project_dir, "test-app", "git@github.com:user/test-app.git")

    config_path = project_dir / "config.yaml"
    assert config_path.is_file()

    config = yaml.safe_load(config_path.read_text())
    assert config["repo_name"] == "test-app"
    assert config["remote_url"] == "git@github.com:user/test-app.git"


def test_write_project_config_no_overwrite(tmp_path: Path) -> None:
    """9.2: write_project_config does not overwrite existing config."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    write_project_config(project_dir, "test-app", "git@github.com:user/test-app.git")
    original_content = (project_dir / "config.yaml").read_text()

    # Call again with different values
    write_project_config(project_dir, "other-app", "git@github.com:user/other-app.git")

    # Content unchanged
    assert (project_dir / "config.yaml").read_text() == original_content


# ── 9.3: Test workspace path for managed repo ───────────────────────


def test_workspace_path_managed_repo_dry_run(tmp_path: Path) -> None:
    """9.3: Dry-run shows workspace path under projects/<name>/workspaces/."""
    from typer.testing import CliRunner

    from action_harness.cli import app

    runner = CliRunner()
    harness_home = tmp_path / "harness"
    project = harness_home / "projects" / "my-app" / "repo"
    project.mkdir(parents=True)
    # Init git repo
    subprocess.run(["git", "init"], cwd=project, capture_output=True, timeout=120)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=project,
        capture_output=True,
        timeout=120,
    )
    # Create openspec change
    change_dir = project / "openspec" / "changes" / "fix-bug"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [ ] task 1\n")
    (change_dir / "proposal.md").write_text("# Proposal\n")

    with patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"):
        result = runner.invoke(
            app,
            [
                "run",
                "--repo",
                str(project),
                "--change",
                "fix-bug",
                "--dry-run",
                "--harness-home",
                str(harness_home),
            ],
        )

    assert result.exit_code == 0
    assert "projects/my-app/workspaces/fix-bug" in result.output


# ── 9.4: Test workspace path for local repo ─────────────────────────


def test_workspace_path_local_repo_dry_run(tmp_path: Path) -> None:
    """9.4: Dry-run for local repo shows /tmp/ workspace path."""
    from typer.testing import CliRunner

    from action_harness.cli import app

    runner = CliRunner()
    repo = tmp_path / "local-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, timeout=120)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=repo,
        capture_output=True,
        timeout=120,
    )
    change_dir = repo / "openspec" / "changes" / "fix-bug"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [ ] task 1\n")
    (change_dir / "proposal.md").write_text("# Proposal\n")

    with patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"):
        result = runner.invoke(
            app,
            ["run", "--repo", str(repo), "--change", "fix-bug", "--dry-run"],
        )

    assert result.exit_code == 0
    assert "/tmp/" in result.output


# ── 9.5: Test manifest written to project runs dir ───────────────────


def test_manifest_project_runs_dir(tmp_path: Path) -> None:
    """9.5: _write_manifest writes to project runs dir when provided."""
    from action_harness.models import RunManifest, WorktreeResult
    from action_harness.pipeline import _write_manifest

    project_runs_dir = tmp_path / "projects" / "my-app" / "runs"
    project_runs_dir.mkdir(parents=True)
    worktree_dir = tmp_path / "worktree"
    worktree_dir.mkdir()

    manifest = RunManifest(
        change_name="fix-bug",
        repo_path=str(worktree_dir),
        started_at="2026-03-16T10:00:00+00:00",
        completed_at="2026-03-16T10:02:00+00:00",
        success=True,
        stages=[WorktreeResult(success=True, worktree_path=worktree_dir)],
        total_duration_seconds=120.0,
    )

    _write_manifest(manifest, worktree_dir, "run-123", project_runs_dir=project_runs_dir)

    # Manifest should be in the project runs dir
    manifest_files = list(project_runs_dir.glob("*.json"))
    assert len(manifest_files) == 1
    assert json.loads(manifest_files[0].read_text())["change_name"] == "fix-bug"

    # Should NOT be in worktree's .action-harness/runs/
    local_runs = worktree_dir / ".action-harness" / "runs"
    assert not local_runs.exists()


# ── 9.6: Test manifest written to worktree for local repo ───────────


def test_manifest_local_repo(tmp_path: Path) -> None:
    """9.6: _write_manifest writes to worktree for local repos (no project_runs_dir)."""
    from action_harness.models import RunManifest, WorktreeResult
    from action_harness.pipeline import _write_manifest

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    manifest = RunManifest(
        change_name="fix-bug",
        repo_path=str(repo_dir),
        started_at="2026-03-16T10:00:00+00:00",
        completed_at="2026-03-16T10:02:00+00:00",
        success=True,
        stages=[WorktreeResult(success=True, worktree_path=repo_dir)],
        total_duration_seconds=120.0,
    )

    _write_manifest(manifest, repo_dir, "run-123")

    local_runs = repo_dir / ".action-harness" / "runs"
    manifest_files = list(local_runs.glob("*.json"))
    assert len(manifest_files) == 1


# ── 9.7: Test list_repos scans projects/ with config gating ─────────


def test_list_repos_projects_with_config_gating(tmp_path: Path) -> None:
    """9.7: list_repos returns only projects with config.yaml."""
    harness_home = tmp_path

    # Project foo: has config.yaml and git repo
    foo_project = harness_home / "projects" / "foo"
    foo_repo = foo_project / "repo"
    _init_git_repo(foo_repo)
    (foo_project / "config.yaml").write_text("repo_name: foo\nremote_url: null\n")

    # Project bar: has config.yaml and git repo
    bar_project = harness_home / "projects" / "bar"
    bar_repo = bar_project / "repo"
    _init_git_repo(bar_repo)
    (bar_project / "config.yaml").write_text("repo_name: bar\nremote_url: null\n")

    # Project broken: no config.yaml
    broken_project = harness_home / "projects" / "broken"
    broken_repo = broken_project / "repo"
    _init_git_repo(broken_repo)

    summaries = list_repos(harness_home)
    assert len(summaries) == 2

    names = {s.name for s in summaries}
    assert names == {"foo", "bar"}

    # Each path should point to projects/<name>/repo/
    for s in summaries:
        assert s.path == harness_home / "projects" / s.name / "repo"


# ── 9.8: Test _is_managed_repo ──────────────────────────────────────


def testis_managed_repo(tmp_path: Path) -> None:
    """9.8: _is_managed_repo returns True for projects/<name>/repo/ path."""
    from action_harness.cli import is_managed_repo

    harness_home = tmp_path / "harness"
    project_repo = harness_home / "projects" / "my-app" / "repo"
    project_repo.mkdir(parents=True)

    assert is_managed_repo(project_repo, harness_home) is True


def test_is_managed_repo_false_for_local(tmp_path: Path) -> None:
    """9.8: _is_managed_repo returns False for local paths."""
    from action_harness.cli import is_managed_repo

    harness_home = tmp_path / "harness"
    harness_home.mkdir()
    local_repo = tmp_path / "my-local-repo"
    local_repo.mkdir()

    assert is_managed_repo(local_repo, harness_home) is False


# ── 9.9: Test clean removes workspace from project dir ───────────────


def test_clean_workspace_project_dir(tmp_path: Path) -> None:
    """9.9: clean --all removes workspaces from projects/ layout."""
    from typer.testing import CliRunner

    from action_harness.cli import app

    runner = CliRunner()
    harness_home = tmp_path / "harness"
    ws_dir = harness_home / "projects" / "app" / "workspaces" / "fix-bug"
    ws_dir.mkdir(parents=True)
    (ws_dir / "some-file.txt").write_text("test")

    result = runner.invoke(app, ["clean", "--all", "--harness-home", str(harness_home)])
    assert result.exit_code == 0
    assert not ws_dir.exists()


# ── 9.10: Test load_manifests with explicit runs_dir ─────────────────


def test_load_manifests_explicit_runs_dir(tmp_path: Path) -> None:
    """9.10: load_manifests reads from explicit runs_dir when provided."""
    runs_dir = tmp_path / "custom-runs"
    runs_dir.mkdir()

    # Write 2 manifest files
    (runs_dir / "run-1.json").write_text(_make_manifest_json(change_name="change-1"))
    (runs_dir / "run-2.json").write_text(_make_manifest_json(change_name="change-2"))

    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    result = load_manifests(repo_path, runs_dir=runs_dir)
    assert len(result) == 2
    names = {m.change_name for m in result}
    assert names == {"change-1", "change-2"}


def test_load_manifests_fallback_to_default(tmp_path: Path) -> None:
    """9.10: load_manifests falls back to .action-harness/runs/ when no runs_dir."""
    default_dir = tmp_path / ".action-harness" / "runs"
    default_dir.mkdir(parents=True)
    (default_dir / "run-1.json").write_text(_make_manifest_json())

    result = load_manifests(tmp_path)
    assert len(result) == 1


# ── Regression: resolve_repo returns project name ────────────────────


def test_resolve_repo_returns_project_name(tmp_path: Path) -> None:
    """resolve_repo returns the project directory name and writes config.yaml."""
    from action_harness.repo import resolve_repo

    harness_home = tmp_path / "harness"

    with (
        patch("action_harness.repo._detect_gh_protocol", return_value="https"),
        patch("action_harness.repo.subprocess.run") as mock_run,
    ):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        path, name = resolve_repo("user/my-app", harness_home)

    assert name == "my-app"
    assert path == harness_home / "projects" / "my-app" / "repo"

    # config.yaml must be written on fresh clone
    config_path = harness_home / "projects" / "my-app" / "config.yaml"
    assert config_path.is_file()
    config = yaml.safe_load(config_path.read_text())
    assert config["repo_name"] == "my-app"
    assert config["remote_url"] == "https://github.com/user/my-app.git"


def test_find_latest_event_log_with_runs_dir(tmp_path: Path) -> None:
    """find_latest_event_log uses explicit runs_dir when provided."""
    from action_harness.progress_feed import find_latest_event_log

    runs_dir = tmp_path / "custom-runs"
    runs_dir.mkdir()
    (runs_dir / "run-1.events.jsonl").write_text('{"event": "test"}\n')

    result = find_latest_event_log(tmp_path, runs_dir=runs_dir)
    assert result is not None
    assert result.name == "run-1.events.jsonl"


def test_find_event_log_by_run_id_with_runs_dir(tmp_path: Path) -> None:
    """find_event_log_by_run_id uses explicit runs_dir when provided."""
    from action_harness.progress_feed import find_event_log_by_run_id

    runs_dir = tmp_path / "custom-runs"
    runs_dir.mkdir()
    (runs_dir / "my-run.events.jsonl").write_text('{"event": "test"}\n')

    result = find_event_log_by_run_id(tmp_path, "my-run", runs_dir=runs_dir)
    assert result is not None
    assert result.name == "my-run.events.jsonl"

    # Non-existent run returns None
    result = find_event_log_by_run_id(tmp_path, "nonexistent", runs_dir=runs_dir)
    assert result is None


def test_clone_or_fetch_precreated_dir_triggers_clone(tmp_path: Path) -> None:
    """_clone_or_fetch clones (not fetches) when repo/ exists but has no .git."""
    from action_harness.repo import _clone_or_fetch

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()  # Pre-created by ensure_project_dir, no .git

    with patch("action_harness.repo.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        _clone_or_fetch("https://github.com/user/app.git", repo_dir, verbose=False)

    # Should have called git clone, not git fetch
    clone_call = mock_run.call_args_list[0]
    assert "clone" in clone_call.args[0]


def test_resolve_repo_collision_returns_owner_repo_name(tmp_path: Path) -> None:
    """resolve_repo collision uses owner-repo as project name."""
    from action_harness.repo import _get_repo_dir

    harness_home = tmp_path / "harness"
    # Create an existing project with a different origin
    existing_project = harness_home / "projects" / "utils"
    existing_repo = existing_project / "repo"
    _init_git_repo(existing_repo)

    with patch("action_harness.repo.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="https://github.com/orgA/utils.git\n",
            stderr="",
        )
        result = _get_repo_dir("orgB", "utils", "https://github.com/orgB/utils.git", harness_home)

    assert result == harness_home / "projects" / "orgB-utils" / "repo"
