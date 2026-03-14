"""End-to-end pipeline wiring."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import typer

from action_harness.evaluator import run_eval
from action_harness.event_log import EventLogger
from action_harness.models import (
    OpenSpecReviewResult,
    PrResult,
    RunManifest,
    StageResultUnion,
    WorkerResult,
)
from action_harness.openspec_reviewer import (
    dispatch_openspec_review,
    parse_review_result,
    push_archive_if_needed,
)
from action_harness.pr import create_pr
from action_harness.profiler import BOOTSTRAP_EVAL_COMMANDS, RepoProfile, profile_repo
from action_harness.worker import count_commits_ahead, dispatch_worker
from action_harness.worktree import cleanup_worktree, create_worktree


def _build_manifest(
    change_name: str,
    repo: Path,
    started_at: str,
    stages: list[StageResultUnion],
    retries: int,
    pr_result: PrResult,
    profile: RepoProfile | None = None,
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
        profile=profile,
    )


def _write_manifest(manifest: RunManifest, repo: Path, run_id: str) -> None:
    """Write manifest JSON to .action-harness/runs/ and set manifest_path.

    Never raises — logs errors to stderr and continues. The manifest is an
    observability artifact; its failure should not mask the pipeline outcome.
    """
    try:
        runs_dir = repo / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)

        safe_name = manifest.change_name.replace("/", "-")
        filename = f"{run_id}.json"
        # Ensure change name is in the filename if not already via run_id
        if safe_name not in run_id:
            filename = f"{run_id}-{safe_name}.json"
        filepath = runs_dir / filename

        manifest.manifest_path = str(filepath)
        filepath.write_text(manifest.model_dump_json(indent=2))
    except Exception as e:
        typer.echo(f"[pipeline] warning: failed to write manifest: {e}", err=True)


def run_pipeline(
    change_name: str,
    repo: Path,
    max_retries: int = 3,
    max_turns: int = 200,
    model: str | None = None,
    effort: str | None = None,
    max_budget_usd: float | None = None,
    permission_mode: str = "bypassPermissions",
    verbose: bool = False,
) -> tuple[PrResult, RunManifest]:
    """Run the full pipeline: worktree -> worker -> eval -> retry -> PR.

    Returns a (PrResult, RunManifest) tuple. The manifest is always written
    to disk, on both success and failure.
    Cleans up worktree on terminal failure (preserves branch for inspection).
    """
    typer.echo(f"[pipeline] starting for change '{change_name}'", err=True)
    typer.echo(f"  max_retries={max_retries}, max_turns={max_turns}", err=True)

    # Profile the repo before the pipeline starts
    try:
        profile = profile_repo(repo)
    except Exception as e:
        typer.echo(f"[pipeline] warning: profiler failed: {e}", err=True)
        profile = RepoProfile(
            ecosystem="unknown",
            eval_commands=list(BOOTSTRAP_EVAL_COMMANDS),
            source="fallback",
        )
    typer.echo(
        f"  profile: ecosystem={profile.ecosystem}, source={profile.source}, "
        f"commands={len(profile.eval_commands)}",
        err=True,
    )

    started_at = datetime.now(UTC).isoformat()
    stages: list[StageResultUnion] = []

    # Generate run_id from started_at (filesystem-safe) + change name
    safe_ts = started_at.replace(":", "-").replace("+", "_")
    safe_change = change_name.replace("/", "-")
    run_id = f"{safe_ts}-{safe_change}"

    # Create event logger before try block so it is available in except/finally
    runs_dir = repo / ".action-harness" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    log_path = runs_dir / f"{run_id}.events.jsonl"
    logger = EventLogger(log_path, run_id)

    logger.emit(
        "run.started",
        change_name=change_name,
        repo_path=str(repo),
        max_retries=max_retries,
    )

    try:
        pr_result = _run_pipeline_inner(
            change_name,
            repo,
            max_retries,
            max_turns,
            model,
            effort,
            max_budget_usd,
            permission_mode,
            verbose,
            stages,
            logger,
            eval_commands=profile.eval_commands,
        )
    except Exception as e:
        typer.echo(f"[pipeline] unexpected error: {e}", err=True)
        logger.emit("pipeline.error", error=str(e))
        pr_result = PrResult(
            success=False, stage="pipeline", error=f"Unexpected error: {e}", branch=""
        )
    finally:
        # Count retries from stages: each WorkerResult after the first is a retry
        worker_count = sum(1 for s in stages if isinstance(s, WorkerResult))
        retries = max(0, worker_count - 1)

        duration = (datetime.now(UTC) - datetime.fromisoformat(started_at)).total_seconds()
        logger.emit(
            "run.completed",
            success=pr_result.success,
            duration_seconds=duration,
            retries=retries,
            error=pr_result.error,
        )
        logger.close()

    manifest = _build_manifest(
        change_name, repo, started_at, stages, retries, pr_result, profile=profile
    )
    manifest.event_log_path = str(log_path)
    _write_manifest(manifest, repo, run_id)

    return pr_result, manifest


def _run_pipeline_inner(
    change_name: str,
    repo: Path,
    max_retries: int,
    max_turns: int,
    model: str | None,
    effort: str | None,
    max_budget_usd: float | None,
    permission_mode: str,
    verbose: bool,
    stages: list[StageResultUnion],
    logger: EventLogger,
    eval_commands: list[str] | None = None,
) -> PrResult:
    """Inner pipeline logic. Appends to stages list as side effect.

    Separated so that run_pipeline can always build and write the manifest
    after this returns, regardless of which exit path is taken.
    """
    # Stage 1: Create worktree
    wt_result = create_worktree(change_name, repo, verbose=verbose)
    stages.append(wt_result)
    if not wt_result.success:
        logger.emit(
            "worktree.failed",
            stage="worktree",
            error=wt_result.error,
        )
        typer.echo(f"[pipeline] failed at worktree stage: {wt_result.error}", err=True)
        return PrResult(
            success=False, stage="pipeline", error=wt_result.error, branch=wt_result.branch
        )

    logger.emit(
        "worktree.created",
        stage="worktree",
        branch=wt_result.branch,
        worktree_path=str(wt_result.worktree_path),
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

        logger.emit("worker.dispatched", stage="worker", attempt=attempt)

        worker_result = dispatch_worker(
            change_name,
            worktree_path,
            base_branch=_get_worktree_base(repo),
            max_turns=max_turns,
            feedback=feedback,
            model=model,
            effort=effort,
            max_budget_usd=max_budget_usd,
            permission_mode=permission_mode,
            verbose=verbose,
        )
        stages.append(worker_result)

        if not worker_result.success:
            logger.emit(
                "worker.failed",
                stage="worker",
                duration_seconds=worker_result.duration_seconds,
                success=False,
                error=worker_result.error,
            )
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
            logger.emit(
                "retry.scheduled",
                attempt=attempt + 1,
                reason="worker_failed",
                max_retries=max_retries,
            )
            attempt += 1
            feedback = worker_result.error
            continue

        logger.emit(
            "worker.completed",
            stage="worker",
            duration_seconds=worker_result.duration_seconds,
            success=True,
            commits_ahead=worker_result.commits_ahead,
            cost_usd=worker_result.cost_usd,
        )

        # Run eval
        actual_commands = eval_commands or BOOTSTRAP_EVAL_COMMANDS
        logger.emit("eval.started", stage="eval", command_count=len(actual_commands))

        eval_result = run_eval(
            worktree_path, eval_commands=eval_commands, verbose=verbose, logger=logger
        )
        stages.append(eval_result)

        logger.emit(
            "eval.completed",
            stage="eval",
            success=eval_result.success,
            commands_passed=eval_result.commands_passed,
            commands_run=eval_result.commands_run,
        )

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

        logger.emit(
            "retry.scheduled",
            attempt=attempt + 1,
            reason="eval_failed",
            max_retries=max_retries,
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
    base_branch = _get_worktree_base(repo)
    pr_result = create_pr(
        change_name,
        worktree_path,
        branch,
        eval_result,
        worker_result=worker_result,
        base_branch=base_branch,
        verbose=verbose,
    )
    stages.append(pr_result)

    if not pr_result.success:
        logger.emit("pr.failed", stage="pr", error=pr_result.error)
        typer.echo(f"[pipeline] PR creation failed: {pr_result.error}", err=True)
        cleanup_worktree(repo, worktree_path, branch, verbose=verbose)
        typer.echo("[pipeline] complete (failed)", err=True)
        return pr_result

    logger.emit(
        "pr.created",
        stage="pr",
        pr_url=pr_result.pr_url,
        branch=pr_result.branch,
    )

    # Stage 5: OpenSpec review
    review_result = _run_openspec_review(
        change_name,
        worktree_path,
        _get_worktree_base(repo),
        max_turns,
        model,
        effort,
        max_budget_usd,
        permission_mode,
        verbose,
        pr_result,
        stages,
        logger,
    )

    if review_result is not None:
        logger.emit(
            "openspec_review.completed",
            stage="openspec-review",
            success=review_result.success,
            duration_seconds=review_result.duration_seconds,
            archived=review_result.archived,
            findings=review_result.findings,
        )

    if review_result is not None and not review_result.success:
        typer.echo("[pipeline] openspec review returned findings", err=True)
        for finding in review_result.findings:
            typer.echo(f"  - {finding}", err=True)
        typer.echo("[pipeline] complete (failed)", err=True)
        return PrResult(
            success=False,
            stage="pipeline",
            error="OpenSpec review returned findings",
            branch=branch,
            pr_url=pr_result.pr_url,
        )

    typer.echo("[pipeline] complete (success)", err=True)
    return pr_result


def _run_openspec_review(
    change_name: str,
    worktree_path: Path,
    base_branch: str,
    max_turns: int,
    model: str | None,
    effort: str | None,
    max_budget_usd: float | None,
    permission_mode: str,
    verbose: bool,
    pr_result: PrResult,
    stages: list[StageResultUnion],
    logger: EventLogger,
) -> OpenSpecReviewResult | None:
    """Run the OpenSpec review stage. Returns the review result, or None on skip."""
    typer.echo("[pipeline] running openspec review", err=True)

    commits_before = count_commits_ahead(worktree_path, base_branch)

    raw_output, duration = dispatch_openspec_review(
        change_name,
        worktree_path,
        base_branch=base_branch,
        max_turns=max_turns,
        model=model,
        effort=effort,
        max_budget_usd=max_budget_usd,
        permission_mode=permission_mode,
        verbose=verbose,
    )

    review_result = parse_review_result(raw_output, duration)
    stages.append(review_result)

    if review_result.success and review_result.archived:
        pushed, push_error = push_archive_if_needed(
            worktree_path, base_branch, commits_before, verbose=verbose
        )
        if push_error:
            typer.echo(f"[pipeline] failed to push archive: {push_error}", err=True)
            review_result = OpenSpecReviewResult(
                success=False,
                error=push_error,
                duration_seconds=review_result.duration_seconds,
                tasks_total=review_result.tasks_total,
                tasks_complete=review_result.tasks_complete,
                validation_passed=review_result.validation_passed,
                semantic_review_passed=review_result.semantic_review_passed,
                findings=review_result.findings,
                archived=review_result.archived,
            )
        elif pushed and pr_result.pr_url:
            # Add a comment on the PR noting the archive was completed
            _comment_archive_complete(worktree_path, pr_result.pr_url, verbose)

    return review_result


def _comment_archive_complete(worktree_path: Path, pr_url: str, verbose: bool) -> None:
    """Add a PR comment noting that OpenSpec archive was completed."""
    comment = "OpenSpec review passed. Archive changes have been pushed to this branch."
    try:
        result = subprocess.run(
            ["gh", "pr", "comment", pr_url, "--body", comment],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            typer.echo(
                f"[pipeline] warning: gh pr comment failed: {result.stderr.strip()}",
                err=True,
            )
        elif verbose:
            typer.echo("[pipeline] posted archive comment on PR", err=True)
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[pipeline] warning: gh pr comment failed: {e}", err=True)


def _get_worktree_base(repo: Path) -> str:
    """Get the base branch name from the worktree module."""
    from action_harness.worktree import _get_default_branch

    return _get_default_branch(repo)
