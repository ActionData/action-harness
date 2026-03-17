"""Dashboard data layer — read-only visibility into harness state.

Pure functions over the filesystem. Each function takes harness_home: Path
and returns Pydantic models. No classes, no state.
"""

import json
import re
import subprocess
import time
from pathlib import Path

import typer

from action_harness.models import (
    ChangeInfo,
    RepoDetail,
    RepoRoadmap,
    RepoSummary,
    WorkspaceInfo,
)
from action_harness.protection import load_protected_patterns

_STALE_THRESHOLD_DAYS = 7


def read_roadmap(repo_path: Path) -> str | None:
    """Read openspec/ROADMAP.md from a repo, or return None if missing."""
    typer.echo(f"[dashboard] reading roadmap from {repo_path}", err=True)
    roadmap_path = repo_path / "openspec" / "ROADMAP.md"
    if not roadmap_path.is_file():
        typer.echo("[dashboard] no ROADMAP.md found", err=True)
        return None
    try:
        content = roadmap_path.read_text(encoding="utf-8")
        typer.echo("[dashboard] roadmap read successfully", err=True)
        return content
    except (OSError, UnicodeDecodeError) as e:
        typer.echo(f"[dashboard] warning: could not read ROADMAP.md: {e}", err=True)
        return None


def read_openspec_changes(repo_path: Path) -> tuple[list[ChangeInfo], int]:
    """Scan openspec/changes/ for active changes and count archived ones.

    Returns (active_changes, completed_count).
    """
    typer.echo(f"[dashboard] reading openspec changes from {repo_path}", err=True)
    changes_dir = repo_path / "openspec" / "changes"
    if not changes_dir.is_dir():
        typer.echo("[dashboard] no openspec/changes/ directory", err=True)
        return [], 0

    # Count completed (archived) changes
    archive_dir = changes_dir / "archive"
    completed_count = 0
    if archive_dir.is_dir():
        completed_count = sum(1 for d in archive_dir.iterdir() if d.is_dir())

    # Scan active changes
    active: list[ChangeInfo] = []
    for entry in sorted(changes_dir.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name == "archive" or entry.name.startswith("."):
            continue

        tasks_md = entry / "tasks.md"
        task_count = 0
        tasks_complete = 0
        if tasks_md.is_file():
            try:
                content = tasks_md.read_text(encoding="utf-8")
                tasks_complete = len(re.findall(r"^- \[x\]", content, re.MULTILINE))
                tasks_incomplete = len(re.findall(r"^- \[ \]", content, re.MULTILINE))
                task_count = tasks_complete + tasks_incomplete
            except (OSError, UnicodeDecodeError) as e:
                typer.echo(
                    f"[dashboard] warning: could not read {tasks_md}: {e}",
                    err=True,
                )

        progress_pct = (tasks_complete / task_count * 100.0) if task_count > 0 else 0.0

        active.append(
            ChangeInfo(
                name=entry.name,
                status="active",
                progress_pct=progress_pct,
                task_count=task_count,
                tasks_complete=tasks_complete,
            )
        )

    typer.echo(
        f"[dashboard] found {len(active)} active, {completed_count} completed changes",
        err=True,
    )
    return active, completed_count


def _get_remote_url(repo_path: Path) -> str | None:
    """Get git remote URL, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
        return None
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None


def _get_workspace_info(
    ws_path: Path, repo_name: str, change_name: str
) -> WorkspaceInfo | None:
    """Build WorkspaceInfo for a single workspace directory."""
    typer.echo(f"[dashboard] inspecting workspace {repo_name}/{change_name}", err=True)

    if not (ws_path / ".git").exists():
        typer.echo(
            f"[dashboard] skipping {repo_name}/{change_name}: not a git worktree",
            err=True,
        )
        return None

    # Get branch
    branch = "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ws_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as e:
        typer.echo(f"[dashboard] warning: git rev-parse failed: {e}", err=True)

    # Get last commit timestamp
    last_commit_age_days = 0
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=ws_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            commit_ts = int(result.stdout.strip())
            age_seconds = time.time() - commit_ts
            last_commit_age_days = max(0, int(age_seconds / 86400))
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired, ValueError) as e:
        typer.echo(f"[dashboard] warning: git log failed: {e}", err=True)

    # Check for open PR (best-effort)
    has_open_pr = False
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--head", branch, "--json", "number", "--limit", "1"],
            cwd=ws_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            pr_data = json.loads(result.stdout.strip())
            if isinstance(pr_data, list) and len(pr_data) > 0:
                has_open_pr = True
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass  # best-effort — stale based on time alone

    # Staleness: >7 days old AND no open PR
    stale = last_commit_age_days > _STALE_THRESHOLD_DAYS and not has_open_pr

    info = WorkspaceInfo(
        repo_name=repo_name,
        change_name=change_name,
        path=ws_path,
        branch=branch,
        last_commit_age_days=last_commit_age_days,
        has_open_pr=has_open_pr,
        stale=stale,
    )
    typer.echo(
        f"[dashboard] workspace {repo_name}/{change_name}: "
        f"branch={branch}, age={last_commit_age_days}d, stale={stale}",
        err=True,
    )
    return info


def list_workspaces(harness_home: Path) -> list[WorkspaceInfo]:
    """List all workspaces across all repos.

    Scans workspaces/<repo_name>/<change_name>/ directories.
    """
    typer.echo(f"[dashboard] listing workspaces from {harness_home}", err=True)
    ws_root = harness_home / "workspaces"
    if not ws_root.is_dir():
        typer.echo("[dashboard] no workspaces/ directory", err=True)
        return []

    workspaces: list[WorkspaceInfo] = []
    for repo_dir in sorted(ws_root.iterdir()):
        if not repo_dir.is_dir():
            continue
        repo_name = repo_dir.name
        for change_dir in sorted(repo_dir.iterdir()):
            if not change_dir.is_dir():
                continue
            info = _get_workspace_info(change_dir, repo_name, change_dir.name)
            if info is not None:
                workspaces.append(info)

    typer.echo(f"[dashboard] found {len(workspaces)} workspaces", err=True)
    return workspaces


def list_repos(harness_home: Path) -> list[RepoSummary]:
    """List all onboarded repos with summary info.

    Scans repos/ dir, skips non-git directories.
    """
    typer.echo(f"[dashboard] listing repos from {harness_home}", err=True)
    repos_dir = harness_home / "repos"
    if not repos_dir.is_dir():
        typer.echo("[dashboard] no repos/ directory", err=True)
        return []

    summaries: list[RepoSummary] = []
    for entry in sorted(repos_dir.iterdir()):
        if not entry.is_dir():
            continue
        # Skip non-git directories
        if not (entry / ".git").exists():
            typer.echo(f"[dashboard] skipping {entry.name}: not a git repo", err=True)
            continue

        remote_url = _get_remote_url(entry)
        has_harness_md = (entry / "HARNESS.md").is_file()
        has_protected_paths = (entry / ".harness" / "protected-paths.yml").is_file()

        # Count workspaces for this repo
        ws_dir = harness_home / "workspaces" / entry.name
        workspace_count = 0
        stale_workspace_count = 0
        if ws_dir.is_dir():
            for ws in ws_dir.iterdir():
                if ws.is_dir():
                    workspace_count += 1
                    info = _get_workspace_info(ws, entry.name, ws.name)
                    if info is not None and info.stale:
                        stale_workspace_count += 1

        # Count OpenSpec changes
        active_changes_list, completed_changes = read_openspec_changes(entry)
        active_changes = len(active_changes_list)

        summaries.append(
            RepoSummary(
                name=entry.name,
                path=entry,
                remote_url=remote_url,
                has_harness_md=has_harness_md,
                has_protected_paths=has_protected_paths,
                workspace_count=workspace_count,
                stale_workspace_count=stale_workspace_count,
                active_changes=active_changes,
                completed_changes=completed_changes,
            )
        )

    typer.echo(f"[dashboard] found {len(summaries)} repos", err=True)
    return summaries


def repo_detail(harness_home: Path, repo_name: str) -> RepoDetail:
    """Get detailed view of a single repo.

    Raises FileNotFoundError if the repo directory doesn't exist.
    """
    typer.echo(f"[dashboard] reading detail for repo {repo_name}", err=True)
    repo_path = harness_home / "repos" / repo_name
    if not repo_path.is_dir():
        raise FileNotFoundError(
            f"Repo '{repo_name}' not found in {harness_home}/repos/"
        )

    # Build summary
    remote_url = _get_remote_url(repo_path)
    has_harness_md = (repo_path / "HARNESS.md").is_file()
    has_protected_paths = (repo_path / ".harness" / "protected-paths.yml").is_file()

    # HARNESS.md content
    harness_md_content: str | None = None
    if has_harness_md:
        try:
            harness_md_content = (repo_path / "HARNESS.md").read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            typer.echo(
                f"[dashboard] warning: could not read HARNESS.md: {e}", err=True
            )

    # Protected patterns
    protected_patterns = load_protected_patterns(repo_path)

    # Workspaces for this repo
    workspaces: list[WorkspaceInfo] = []
    ws_dir = harness_home / "workspaces" / repo_name
    stale_workspace_count = 0
    if ws_dir.is_dir():
        for ws in sorted(ws_dir.iterdir()):
            if ws.is_dir():
                info = _get_workspace_info(ws, repo_name, ws.name)
                if info is not None:
                    workspaces.append(info)
                    if info.stale:
                        stale_workspace_count += 1

    # OpenSpec changes
    active_changes_list, completed_changes = read_openspec_changes(repo_path)

    # Roadmap
    roadmap_content = read_roadmap(repo_path)

    summary = RepoSummary(
        name=repo_name,
        path=repo_path,
        remote_url=remote_url,
        has_harness_md=has_harness_md,
        has_protected_paths=has_protected_paths,
        workspace_count=len(workspaces),
        stale_workspace_count=stale_workspace_count,
        active_changes=len(active_changes_list),
        completed_changes=completed_changes,
    )

    detail = RepoDetail(
        summary=summary,
        harness_md_content=harness_md_content,
        protected_patterns=protected_patterns,
        workspaces=workspaces,
        roadmap_content=roadmap_content,
        openspec_changes=active_changes_list,
        completed_changes=completed_changes,
    )

    typer.echo(f"[dashboard] detail for {repo_name} complete", err=True)
    return detail


def cross_repo_roadmap(harness_home: Path) -> list[RepoRoadmap]:
    """Cross-repo OpenSpec roadmap view.

    For each onboarded repo, read ROADMAP.md and enumerate active changes.
    """
    typer.echo(f"[dashboard] building cross-repo roadmap from {harness_home}", err=True)
    repos_dir = harness_home / "repos"
    if not repos_dir.is_dir():
        typer.echo("[dashboard] no repos/ directory", err=True)
        return []

    roadmaps: list[RepoRoadmap] = []
    for entry in sorted(repos_dir.iterdir()):
        if not entry.is_dir():
            continue
        if not (entry / ".git").exists():
            continue

        roadmap_content = read_roadmap(entry)
        active_changes, completed_count = read_openspec_changes(entry)

        roadmaps.append(
            RepoRoadmap(
                repo_name=entry.name,
                roadmap_content=roadmap_content,
                active_changes=active_changes,
                completed_count=completed_count,
            )
        )

    typer.echo(f"[dashboard] built roadmap for {len(roadmaps)} repos", err=True)
    return roadmaps
