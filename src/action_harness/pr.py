"""PR creation via gh CLI."""

import re
import subprocess
from pathlib import Path

import typer

from action_harness.models import EvalResult, PrResult, WorkerResult


def _read_proposal_why(worktree_path: Path, change_name: str) -> str | None:
    """Read the Why section from the change's proposal.md.

    Extracts text between the ``## Why`` heading and the next ``##``-level
    heading (or end of file). Returns None if the file is missing or the
    section is not found.
    """
    proposal_path = worktree_path / "openspec" / "changes" / change_name / "proposal.md"
    try:
        text = proposal_path.read_text()
    except (FileNotFoundError, OSError):
        return None

    match = re.search(r"^## Why\s*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        return None

    content = match.group(1).strip()
    return content if content else None


def _get_diff_stat(worktree_path: Path, base_branch: str) -> str | None:
    """Run ``git diff --stat`` against the base branch and return the output.

    Uses ``origin/<base_branch>`` because worktrees may not have a local ref
    for the base branch. Truncates to 30 lines if longer. Returns None on
    failure.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", f"origin/{base_branch}..HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return None

    if result.returncode != 0:
        return None

    output = result.stdout.strip()
    if not output:
        return None

    lines = output.splitlines()
    if len(lines) > 30:
        return "\n".join(lines[:30]) + "\n... (truncated)"
    return output


def _get_commit_log(worktree_path: Path, base_branch: str) -> str | None:
    """Run ``git log --oneline`` for commits on the branch.

    Returns None if the output is empty or the command fails.
    """
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"origin/{base_branch}..HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return None

    if result.returncode != 0:
        return None

    output = result.stdout.strip()
    return output if output else None


def create_pr(
    change_name: str,
    worktree_path: Path,
    branch: str,
    eval_result: EvalResult,
    worker_result: WorkerResult | None = None,
    base_branch: str = "main",
    verbose: bool = False,
) -> PrResult:
    """Push branch and open a PR via gh CLI.

    Pushes the worktree branch to origin, then creates a PR with a structured
    title and body. Returns the PR URL.

    Note: git and gh CLI availability is validated by cli.validate_inputs before
    the pipeline starts. This function assumes both are in PATH.
    """
    typer.echo(f"[pr] creating PR for '{change_name}' on branch '{branch}'", err=True)

    # Push branch to remote
    try:
        push_result = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[pr] ERROR: git push failed: {e}", err=True)
        return PrResult(
            success=False,
            stage="pr",
            error=f"git push failed: {e}",
            branch=branch,
        )

    if push_result.returncode != 0:
        typer.echo(f"[pr] push failed: {push_result.stderr.strip()}", err=True)
        return PrResult(
            success=False,
            stage="pr",
            error=f"git push failed: {push_result.stderr.strip()}",
            branch=branch,
        )

    if verbose:
        typer.echo(f"  pushed to origin/{branch}", err=True)

    # Build PR body
    title = f"[harness] {change_name}"
    body = _build_pr_body(change_name, eval_result, worktree_path, base_branch, worker_result)

    if verbose:
        typer.echo(f"  title: {title}", err=True)

    # Create PR via gh CLI
    try:
        gh_result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--head",
                branch,
            ],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[pr] ERROR: gh pr create failed: {e}", err=True)
        return PrResult(
            success=False,
            stage="pr",
            error=f"gh pr create failed: {e}",
            branch=branch,
        )

    if gh_result.returncode != 0:
        typer.echo(f"[pr] gh pr create failed: {gh_result.stderr.strip()}", err=True)
        return PrResult(
            success=False,
            stage="pr",
            error=f"gh pr create failed: {gh_result.stderr.strip()}",
            branch=branch,
        )

    pr_url = gh_result.stdout.strip()
    typer.echo(pr_url)  # Final output to stdout
    typer.echo(f"[pr] created: {pr_url}", err=True)

    return PrResult(
        success=True,
        stage="pr",
        pr_url=pr_url,
        branch=branch,
    )


def _build_pr_body(
    change_name: str,
    eval_result: EvalResult,
    worktree_path: Path,
    base_branch: str,
    worker_result: WorkerResult | None = None,
) -> str:
    """Build structured PR body with enriched context."""
    sections: list[str] = [f"## Change: {change_name}\n"]

    # Background — from proposal Why section
    why = _read_proposal_why(worktree_path, change_name)
    if why:
        sections.append(f"### Background\n{why}\n")

    # Changes — diff stat
    diff_stat = _get_diff_stat(worktree_path, base_branch)
    if diff_stat:
        sections.append(f"### Changes\n```\n{diff_stat}\n```\n")

    # Commits — log
    commit_log = _get_commit_log(worktree_path, base_branch)
    if commit_log:
        sections.append(f"### Commits\n```\n{commit_log}\n```\n")

    # Worker metadata
    if worker_result is not None:
        worker_lines: list[str] = []
        if worker_result.cost_usd is not None:
            worker_lines.append(f"- **Cost:** ${worker_result.cost_usd:.2f}")
        if worker_result.duration_seconds is not None:
            worker_lines.append(f"- **Duration:** {worker_result.duration_seconds:.0f}s")
        if worker_result.worker_output:
            obs = worker_result.worker_output
            if len(obs) > 500:
                obs = obs[:500] + "... (truncated)"
            worker_lines.append(f"- **Observations:** {obs}")
        if worker_lines:
            sections.append("### Worker\n" + "\n".join(worker_lines) + "\n")

    # Eval results
    if eval_result.success:
        eval_summary = (
            f"All {eval_result.commands_passed}/{eval_result.commands_run} eval commands passed"
        )
    else:
        failed = eval_result.failed_command or "unknown"
        eval_summary = (
            f"{eval_result.commands_passed}/{eval_result.commands_run} "
            f"eval commands passed (failed: {failed})"
        )
    sections.append(f"### Eval Results\n{eval_summary}\n")

    # Footer
    sections.append("---\nGenerated by action-harness")

    return "\n".join(sections)
