"""End-to-end pipeline wiring."""

from pathlib import Path

import typer

from action_harness.evaluator import run_eval
from action_harness.models import PrResult
from action_harness.pr import create_pr
from action_harness.worker import dispatch_worker
from action_harness.worktree import cleanup_worktree, create_worktree


def run_pipeline(
    change_name: str,
    repo: Path,
    max_retries: int = 3,
    max_turns: int = 200,
    verbose: bool = False,
) -> PrResult:
    """Run the full pipeline: worktree → worker → eval → retry → PR.

    Returns a PrResult on success, or a PrResult with success=False on failure.
    Cleans up worktree on terminal failure (preserves branch for inspection).
    """
    typer.echo(f"[pipeline] starting for change '{change_name}'", err=True)
    typer.echo(f"  max_retries={max_retries}, max_turns={max_turns}", err=True)

    # Stage 1: Create worktree
    wt_result = create_worktree(change_name, repo, verbose=verbose)
    if not wt_result.success:
        typer.echo(f"[pipeline] failed at worktree stage: {wt_result.error}", err=True)
        return PrResult(
            success=False, stage="pipeline", error=wt_result.error, branch=wt_result.branch
        )

    assert wt_result.worktree_path is not None
    worktree_path = wt_result.worktree_path
    branch = wt_result.branch

    # Stage 2+3: Worker dispatch + eval with retry loop
    attempt = 0
    feedback: str | None = None

    while attempt <= max_retries:
        # Dispatch worker
        if feedback:
            typer.echo(f"[pipeline] retry {attempt}/{max_retries} with feedback", err=True)

        worker_result = dispatch_worker(
            change_name,
            worktree_path,
            base_branch=_get_worktree_base(repo),
            max_turns=max_turns,
            feedback=feedback,
            verbose=verbose,
        )

        if not worker_result.success:
            if attempt >= max_retries:
                typer.echo(
                    f"[pipeline] worker failed after {attempt + 1} attempt(s): "
                    f"{worker_result.error}",
                    err=True,
                )
                cleanup_worktree(repo, worktree_path, branch, verbose=verbose)
                return PrResult(
                    success=False,
                    stage="pipeline",
                    error=f"Worker failed: {worker_result.error}",
                    branch=branch,
                )
            attempt += 1
            feedback = worker_result.error
            continue

        # Run eval
        eval_result = run_eval(worktree_path, verbose=verbose)

        if eval_result.success:
            typer.echo("[pipeline] eval passed, creating PR", err=True)
            break

        # Eval failed — retry with feedback
        if attempt >= max_retries:
            typer.echo(
                f"[pipeline] eval failed after {attempt + 1} attempt(s): {eval_result.error}",
                err=True,
            )
            cleanup_worktree(repo, worktree_path, branch, verbose=verbose)
            return PrResult(
                success=False,
                stage="pipeline",
                error=f"Eval failed after {attempt + 1} attempts: {eval_result.error}",
                branch=branch,
            )

        attempt += 1
        feedback = eval_result.feedback_prompt
    else:
        # Should not reach here, but safety net
        cleanup_worktree(repo, worktree_path, branch, verbose=verbose)
        return PrResult(
            success=False,
            stage="pipeline",
            error="Max retries exceeded",
            branch=branch,
        )

    # Stage 4: Create PR
    pr_result = create_pr(change_name, worktree_path, branch, eval_result, verbose=verbose)

    if not pr_result.success:
        typer.echo(f"[pipeline] PR creation failed: {pr_result.error}", err=True)
        cleanup_worktree(repo, worktree_path, branch, verbose=verbose)
        typer.echo("[pipeline] complete (failed)", err=True)
    else:
        typer.echo("[pipeline] complete (success)", err=True)

    return pr_result


def _get_worktree_base(repo: Path) -> str:
    """Get the base branch name from the worktree module."""
    from action_harness.worktree import _get_default_branch

    return _get_default_branch(repo)
