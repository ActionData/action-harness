"""Git worktree management."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import typer

from action_harness.models import StageResult, WorktreeResult


def _get_default_branch(repo: Path) -> str:
    """Get the default branch name for a repo."""
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        # refs/remotes/origin/main -> main
        return result.stdout.strip().split("/")[-1]
    # Fallback: try common defaults
    for branch in ("main", "master"):
        check = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if check.returncode == 0:
            return branch
    return "main"


def _cleanup_existing_branch(repo: Path, branch: str, verbose: bool = False) -> None:
    """Remove existing worktree and branch if they exist from a prior run."""
    # Prune stale worktree metadata first (handles manually deleted worktree dirs)
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    # Remove worktree if it exists
    list_result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    for line in list_result.stdout.splitlines():
        if line.startswith("worktree "):
            wt_path = line.split(" ", 1)[1]
            # Check if this worktree uses our branch
            check = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=wt_path,
                capture_output=True,
                text=True,
            )
            if check.returncode == 0 and check.stdout.strip() == branch:
                if verbose:
                    typer.echo(f"  removing existing worktree at {wt_path}", err=True)
                rm_result = subprocess.run(
                    ["git", "worktree", "remove", "--force", wt_path],
                    cwd=repo,
                    capture_output=True,
                    text=True,
                )
                if rm_result.returncode != 0:
                    typer.echo(
                        f"[worktree] warning: failed to remove worktree: "
                        f"{rm_result.stderr.strip()}",
                        err=True,
                    )

    # Delete branch if it exists
    check = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if check.returncode == 0:
        if verbose:
            typer.echo(f"  deleting existing branch {branch}", err=True)
        del_result = subprocess.run(
            ["git", "branch", "-D", branch],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if del_result.returncode != 0:
            typer.echo(
                f"[worktree] warning: failed to delete branch: {del_result.stderr.strip()}",
                err=True,
            )


def create_worktree(change_name: str, repo: Path, verbose: bool = False) -> WorktreeResult:
    """Create a git worktree for the given change.

    Creates a worktree branched from the default branch with branch name
    harness/<change-name>. If the branch already exists from a prior run,
    cleans up the old worktree and branch first.
    """
    branch = f"harness/{change_name}"
    typer.echo(f"[worktree] creating worktree for '{change_name}'", err=True)

    # Clean up any existing branch/worktree from prior runs
    _cleanup_existing_branch(repo, branch, verbose=verbose)

    # Determine base branch and worktree path
    base_branch = _get_default_branch(repo)
    worktree_dir = Path(tempfile.mkdtemp(prefix="action-harness-"))
    worktree_path = worktree_dir / change_name

    if verbose:
        typer.echo(f"  base branch: {base_branch}", err=True)
        typer.echo(f"  worktree path: {worktree_path}", err=True)

    # Create the worktree
    result = subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(worktree_path), base_branch],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        typer.echo(f"[worktree] failed: {result.stderr.strip()}", err=True)
        # Clean up the leaked temp directory
        shutil.rmtree(worktree_dir, ignore_errors=True)
        return WorktreeResult(
            success=False,
            stage="worktree",
            error=f"Failed to create worktree: {result.stderr.strip()}",
            branch=branch,
        )

    typer.echo(f"[worktree] created at {worktree_path} (branch: {branch})", err=True)
    return WorktreeResult(
        success=True,
        stage="worktree",
        worktree_path=worktree_path,
        branch=branch,
    )


def cleanup_worktree(
    repo: Path,
    worktree_path: Path,
    branch: str,
    preserve_branch: bool = True,
    verbose: bool = False,
) -> StageResult:
    """Remove a worktree. Optionally preserve the branch for inspection.

    On terminal failure: remove worktree, preserve branch for inspection.
    On PR creation: worktree is preserved (caller doesn't call this).
    """
    typer.echo(f"[worktree] cleaning up {worktree_path}", err=True)

    result = subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        typer.echo(
            f"[worktree] warning: worktree remove failed: {result.stderr.strip()}",
            err=True,
        )

    # Clean up parent temp directory
    parent = worktree_path.parent
    if parent.name.startswith("action-harness-") and parent.exists():
        shutil.rmtree(parent, ignore_errors=True)

    if not preserve_branch:
        del_result = subprocess.run(
            ["git", "branch", "-D", branch],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if del_result.returncode != 0:
            typer.echo(
                f"[worktree] warning: branch delete failed: {del_result.stderr.strip()}",
                err=True,
            )
        elif verbose:
            typer.echo(f"  deleted branch {branch}", err=True)

    typer.echo("[worktree] cleanup complete", err=True)
    return StageResult(success=True, stage="worktree-cleanup")
