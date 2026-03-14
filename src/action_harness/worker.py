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
        typer.echo(
            f"[worker] warning: git rev-list failed: {result.stderr.strip()}",
            err=True,
        )
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        typer.echo(
            f"[worker] warning: unexpected git rev-list output: {result.stdout.strip()}",
            err=True,
        )
        return 0


def dispatch_worker(
    change_name: str,
    worktree_path: Path,
    base_branch: str = "main",
    max_turns: int = 200,
    feedback: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    max_budget_usd: float | None = None,
    permission_mode: str = "bypassPermissions",
    verbose: bool = False,
) -> WorkerResult:
    """Dispatch a Claude Code worker to implement a change.

    Invokes the claude CLI as a subprocess in the worktree directory.
    Captures JSON output and verifies the worker produced commits.

    Note: claude CLI availability is validated by cli.validate_inputs before
    the pipeline starts. This function assumes claude is in PATH.
    """
    typer.echo(f"[worker] dispatching for '{change_name}'", err=True)

    system_prompt = build_system_prompt(change_name)
    # claude CLI: -p sends the user prompt, --system-prompt sets the system prompt.
    # The system prompt provides role instructions; the user prompt is the task directive.
    user_prompt = f"Implement the OpenSpec change '{change_name}' using the opsx:apply skill."
    if feedback:
        user_prompt = f"{user_prompt}\n\n{feedback}"
    cmd = [
        "claude",
        "-p",
        user_prompt,
        "--system-prompt",
        system_prompt,
        "--output-format",
        "json",
        "--max-turns",
        str(max_turns),
        "--permission-mode",
        permission_mode,
    ]
    if model is not None:
        cmd.extend(["--model", model])
    if effort is not None:
        cmd.extend(["--effort", effort])
    if max_budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(max_budget_usd)])

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

    # Check for commits against the base branch (provided by the pipeline from worktree creation)
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
