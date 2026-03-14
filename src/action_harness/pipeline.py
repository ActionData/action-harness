"""End-to-end pipeline wiring."""

from datetime import UTC, datetime
from pathlib import Path

import typer

from action_harness.evaluator import run_eval
from action_harness.models import (
    PrResult,
    RunManifest,
    StageResultUnion,
    WorkerResult,
)
from action_harness.pr import create_pr
from action_harness.worker import dispatch_worker
from action_harness.worktree import cleanup_worktree, create_worktree


def _build_manifest(
    change_name: str,
    repo: Path,
    started_at: str,
    stages: list[StageResultUnion],
    retries: int,
    pr_result: PrResult,
) -> RunManifest:
    """Construct a RunManifest from collected stage data."""
    completed_at = datetime.now(UTC).isoformat()
    start_dt = datetime.fromisoformat(started_at)
    end_dt = datetime.fromisoformat(completed_at)
    total_duration = (end_dt - start_dt).total_seconds()

    # Sum cost_usd across all WorkerResult entries (including retries)
    total_cost: float | None = None
    for stage in stages:
        if isinstance(stage, WorkerResult) and stage.cost_usd is not None:
            if total_cost is None:
                total_cost = 0.0
            total_cost += stage.cost_usd

    return RunManifest(
        change_name=change_name,
        repo_path=str(repo),
        started_at=started_at,
        completed_at=completed_at,
        success=pr_result.success,
        stages=stages,
        total_duration_seconds=total_duration,
        total_cost_usd=total_cost,
        retries=retries,
        pr_url=pr_result.pr_url if pr_result.success else None,
        error=pr_result.error if not pr_result.success else None,
    )


def _write_manifest(manifest: RunManifest, repo: Path) -> None:
    """Write manifest JSON to .action-harness/runs/ and set manifest_path."""
    runs_dir = repo / ".action-harness" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Replace colons and plus signs to make filesystem-safe
    ts = manifest.completed_at.replace(":", "-").replace("+", "_")
    filename = f"{ts}-{manifest.change_name}.json"
    filepath = runs_dir / filename

    manifest.manifest_path = str(filepath)
    filepath.write_text(manifest.model_dump_json(indent=2))


def run_pipeline(
    change_name: str,
    repo: Path,
    max_retries: int = 3,
    max_turns: int = 200,
    verbose: bool = False,
) -> tuple[PrResult, RunManifest]:
    """Run the full pipeline: worktree -> worker -> eval -> retry -> PR.

    Returns a (PrResult, RunManifest) tuple. The manifest is always written
    to disk, on both success and failure.
    Cleans up worktree on terminal failure (preserves branch for inspection).
    """
    typer.echo(f"[pipeline] starting for change '{change_name}'", err=True)
    typer.echo(f"  max_retries={max_retries}, max_turns={max_turns}", err=True)

    started_at = datetime.now(UTC).isoformat()
    stages: list[StageResultUnion] = []

    try:
        pr_result = _run_pipeline_inner(change_name, repo, max_retries, max_turns, verbose, stages)
    except Exception as e:
        typer.echo(f"[pipeline] unexpected error: {e}", err=True)
        pr_result = PrResult(
            success=False, stage="pipeline", error=f"Unexpected error: {e}", branch=""
        )

    # Count retries from stages: each WorkerResult after the first is a retry
    worker_count = sum(1 for s in stages if isinstance(s, WorkerResult))
    retries = max(0, worker_count - 1)

    manifest = _build_manifest(change_name, repo, started_at, stages, retries, pr_result)
    _write_manifest(manifest, repo)

    return pr_result, manifest


def _run_pipeline_inner(
    change_name: str,
    repo: Path,
    max_retries: int,
    max_turns: int,
    verbose: bool,
    stages: list[StageResultUnion],
) -> PrResult:
    """Inner pipeline logic. Appends to stages list as side effect.

    Separated so that run_pipeline can always build and write the manifest
    after this returns, regardless of which exit path is taken.
    """
    # Stage 1: Create worktree
    wt_result = create_worktree(change_name, repo, verbose=verbose)
    stages.append(wt_result)
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
        stages.append(worker_result)

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
        stages.append(eval_result)

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
    stages.append(pr_result)

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
