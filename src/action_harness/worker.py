"""Claude Code CLI dispatch."""

import json
import subprocess
import time
from pathlib import Path

import typer

from action_harness.models import WorkerResult


def build_system_prompt(change_name: str) -> str:
    """Build the system prompt for a Claude Code worker."""
    return (
        f"You are implementing the OpenSpec change '{change_name}'. "
        f"Run the opsx:apply skill to implement all tasks for this change. "
        f"Commit your work incrementally as you complete each task. "
        f"After implementation, exercise the feature you built and report "
        f"what you tested and observed."
    )


def count_commits_ahead(worktree_path: Path, base_branch: str) -> int:
    """Count how many commits the worktree branch is ahead of the base branch."""
    result = subprocess.run(
        ["git", "rev-list", "--count", f"{base_branch}..HEAD"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def _get_base_branch(worktree_path: Path) -> str:
    """Determine the base branch for commit counting."""
    for branch in ("main", "master"):
        check = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if check.returncode == 0:
            return branch
    return "main"


def dispatch_worker(
    change_name: str,
    worktree_path: Path,
    max_turns: int = 200,
    verbose: bool = False,
) -> WorkerResult:
    """Dispatch a Claude Code worker to implement a change.

    Invokes the claude CLI as a subprocess in the worktree directory.
    Captures JSON output and verifies the worker produced commits.
    """
    typer.echo(f"[worker] dispatching for '{change_name}'", err=True)

    system_prompt = build_system_prompt(change_name)
    cmd = [
        "claude",
        "-p",
        system_prompt,
        "--output-format",
        "json",
        "--max-turns",
        str(max_turns),
    ]

    if verbose:
        typer.echo(f"  cwd: {worktree_path}", err=True)
        typer.echo(f"  cmd: {' '.join(cmd[:6])}...", err=True)

    start_time = time.monotonic()

    result = subprocess.run(
        cmd,
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    duration = time.monotonic() - start_time

    # Parse JSON output
    cost_usd = None
    worker_output = None
    if result.stdout:
        try:
            output_data = json.loads(result.stdout)
            cost_usd = output_data.get("cost_usd")
            worker_output = output_data.get("result")
        except json.JSONDecodeError:
            worker_output = result.stdout[:500]

    if result.returncode != 0:
        typer.echo(f"[worker] failed (exit {result.returncode})", err=True)
        return WorkerResult(
            success=False,
            stage="worker",
            error=f"Claude CLI exited with code {result.returncode}: {result.stderr[:500]}",
            duration_seconds=duration,
            cost_usd=cost_usd,
            worker_output=worker_output,
        )

    # Check for commits
    base_branch = _get_base_branch(worktree_path)
    commits = count_commits_ahead(worktree_path, base_branch)

    if commits == 0:
        typer.echo("[worker] completed but produced no commits", err=True)
        return WorkerResult(
            success=False,
            stage="worker",
            error="No commits were produced. Review the change specs "
            "and implement the required tasks.",
            duration_seconds=duration,
            commits_ahead=0,
            cost_usd=cost_usd,
            worker_output=worker_output,
        )

    typer.echo(
        f"[worker] completed: {commits} commit(s), ${cost_usd or '?'}",
        err=True,
    )
    return WorkerResult(
        success=True,
        stage="worker",
        duration_seconds=duration,
        commits_ahead=commits,
        cost_usd=cost_usd,
        worker_output=worker_output,
    )
