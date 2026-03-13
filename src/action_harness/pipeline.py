"""End-to-end pipeline wiring."""

import os
from datetime import UTC, datetime
from pathlib import Path

import typer

from action_harness.evaluator import run_eval
from action_harness.models import PrResult, RunManifest, StageResult, WorkerResult
from action_harness.pr import create_pr
from action_harness.worker import dispatch_worker
from action_harness.worktree import cleanup_worktree, create_worktree


def _build_manifest(
    change_name: str,
    repo: Path,
    started_at: str,
    stages: list[StageResult],
    retries: int,
    pr_result: PrResult | None,
) -> RunManifest:
    """Construct a RunManifest from collected pipeline data."""
    completed_at = datetime.now(UTC).isoformat()
    started_dt = datetime.fromisoformat(started_at)
    completed_dt = datetime.fromisoformat(completed_at)
    total_duration_seconds = (completed_dt - started_dt).total_seconds()

    # Sum cost_usd across ALL WorkerResult entries (including retries)
    total_cost_usd: float | None = None
    for stage in stages:
        if isinstance(stage, WorkerResult) and stage.cost_usd is not None:
            if total_cost_usd is None:
                total_cost_usd = 0.0
            total_cost_usd += stage.cost_usd

    success = pr_result.success if pr_result is not None else False
    error = pr_result.error if pr_result is not None and not pr_result.success else None
    pr_url = pr_result.pr_url if pr_result is not None else None

    # If no pr_result, derive error from the last failed stage
    if pr_result is None and stages:
        last = stages[-1]
        if not last.success:
            error = last.error

    return RunManifest(
        change_name=change_name,
        repo_path=str(repo),
        started_at=started_at,
        completed_at=completed_at,
        success=success,
        stages=stages,
        total_duration_seconds=total_duration_seconds,
        total_cost_usd=total_cost_usd,
        retries=retries,
        pr_url=pr_url,
        error=error,
    )


def _write_manifest(manifest: RunManifest, repo: Path) -> RunManifest:
    """Write manifest JSON to disk and return manifest with path set."""
    runs_dir = repo / ".action-harness" / "runs"
    os.makedirs(runs_dir, exist_ok=True)

    # Use started_at timestamp for filename (sanitize colons for filesystem)
    timestamp = manifest.started_at.replace(":", "-").replace("+", "-")
    filename = f"{timestamp}-{manifest.change_name}.json"
    manifest_path = runs_dir / filename

    # Set path before serializing so it appears in the JSON
    manifest.manifest_path = str(manifest_path)
    manifest_path.write_text(manifest.model_dump_json(indent=2))
    typer.echo(f"[pipeline] manifest written to {manifest_path}", err=True)

    return manifest


def run_pipeline(
    change_name: str,
    repo: Path,
    max_retries: int = 3,
    max_turns: int = 200,
    verbose: bool = False,
) -> tuple[PrResult, RunManifest]:
    """Run the full pipeline: worktree -> worker -> eval -> retry -> PR.

    Returns a (PrResult, RunManifest) tuple. The manifest is always written
    to disk, even on failure.
    """
    typer.echo(f"[pipeline] starting for change '{change_name}'", err=True)
    typer.echo(f"  max_retries={max_retries}, max_turns={max_turns}", err=True)

    started_at = datetime.now(UTC).isoformat()
    stages: list[StageResult] = []
    retries = 0

    # Stage 1: Create worktree
    wt_result = create_worktree(change_name, repo, verbose=verbose)
    stages.append(wt_result)
    if not wt_result.success:
        typer.echo(f"[pipeline] failed at worktree stage: {wt_result.error}", err=True)
        pr_result = PrResult(
            success=False, stage="pipeline", error=wt_result.error, branch=wt_result.branch
        )
        manifest = _build_manifest(change_name, repo, started_at, stages, retries, pr_result)
        manifest = _write_manifest(manifest, repo)
        return pr_result, manifest

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
                pr_result = PrResult(
                    success=False,
                    stage="pipeline",
                    error=f"Worker failed: {worker_result.error}",
                    branch=branch,
                )
                manifest = _build_manifest(
                    change_name, repo, started_at, stages, retries, pr_result
                )
                manifest = _write_manifest(manifest, repo)
                return pr_result, manifest
            attempt += 1
            retries += 1
            feedback = worker_result.error
            continue

        # Run eval
        eval_result = run_eval(worktree_path, verbose=verbose)
        stages.append(eval_result)

        if eval_result.success:
            typer.echo("[pipeline] eval passed, creating PR", err=True)
            break

        # Eval failed -- retry with feedback
        if attempt >= max_retries:
            typer.echo(
                f"[pipeline] eval failed after {attempt + 1} attempt(s): {eval_result.error}",
                err=True,
            )
            cleanup_worktree(repo, worktree_path, branch, verbose=verbose)
            pr_result = PrResult(
                success=False,
                stage="pipeline",
                error=f"Eval failed after {attempt + 1} attempts: {eval_result.error}",
                branch=branch,
            )
            manifest = _build_manifest(change_name, repo, started_at, stages, retries, pr_result)
            manifest = _write_manifest(manifest, repo)
            return pr_result, manifest

        attempt += 1
        retries += 1
        feedback = eval_result.feedback_prompt
    else:
        # Should not reach here, but safety net
        cleanup_worktree(repo, worktree_path, branch, verbose=verbose)
        pr_result = PrResult(
            success=False,
            stage="pipeline",
            error="Max retries exceeded",
            branch=branch,
        )
        manifest = _build_manifest(change_name, repo, started_at, stages, retries, pr_result)
        manifest = _write_manifest(manifest, repo)
        return pr_result, manifest

    # Stage 4: Create PR
    pr_result = create_pr(change_name, worktree_path, branch, eval_result, verbose=verbose)
    stages.append(pr_result)

    if not pr_result.success:
        typer.echo(f"[pipeline] PR creation failed: {pr_result.error}", err=True)
        cleanup_worktree(repo, worktree_path, branch, verbose=verbose)
        typer.echo("[pipeline] complete (failed)", err=True)
    else:
        typer.echo("[pipeline] complete (success)", err=True)

    manifest = _build_manifest(change_name, repo, started_at, stages, retries, pr_result)
    manifest = _write_manifest(manifest, repo)
    return pr_result, manifest


def _get_worktree_base(repo: Path) -> str:
    """Get the base branch name from the worktree module."""
    from action_harness.worktree import _get_default_branch

    return _get_default_branch(repo)
