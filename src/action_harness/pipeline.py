"""End-to-end pipeline wiring."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import typer

from action_harness.evaluator import run_eval
from action_harness.models import (
    OpenSpecReviewResult,
    PrResult,
    ReviewResult,
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
from action_harness.review_agents import (
    dispatch_review_agents,
    format_review_feedback,
    triage_findings,
)
from action_harness.worker import count_commits_ahead, dispatch_worker
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

    # Sum cost_usd across WorkerResult and ReviewResult entries
    total_cost: float | None = None
    for stage in stages:
        cost = None
        if isinstance(stage, (WorkerResult, ReviewResult)):
            cost = stage.cost_usd
        if cost is not None:
            if total_cost is None:
                total_cost = 0.0
            total_cost += cost

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
    """Write manifest JSON to .action-harness/runs/ and set manifest_path.

    Never raises — logs errors to stderr and continues. The manifest is an
    observability artifact; its failure should not mask the pipeline outcome.
    """
    try:
        runs_dir = repo / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)

        # Replace colons, plus signs, and slashes to make filesystem-safe
        ts = manifest.completed_at.replace(":", "-").replace("+", "_")
        safe_name = manifest.change_name.replace("/", "-")
        filename = f"{ts}-{safe_name}.json"
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
    skip_review: bool = False,
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
            skip_review=skip_review,
        )
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
    model: str | None,
    effort: str | None,
    max_budget_usd: float | None,
    permission_mode: str,
    verbose: bool,
    stages: list[StageResultUnion],
    *,
    skip_review: bool = False,
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
            model=model,
            effort=effort,
            max_budget_usd=max_budget_usd,
            permission_mode=permission_mode,
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
        typer.echo(f"[pipeline] PR creation failed: {pr_result.error}", err=True)
        cleanup_worktree(repo, worktree_path, branch, verbose=verbose)
        typer.echo("[pipeline] complete (failed)", err=True)
        return pr_result

    # Stage 5: Review agents (parallel code review)
    if not skip_review:
        needs_fix = _run_review_agents(
            pr_result,
            worktree_path,
            max_turns,
            model,
            effort,
            max_budget_usd,
            permission_mode,
            verbose,
            stages,
        )

        if needs_fix:
            _run_review_fix_retry(
                change_name,
                pr_result,
                worktree_path,
                repo,
                max_turns,
                model,
                effort,
                max_budget_usd,
                permission_mode,
                verbose,
                stages,
            )
    else:
        typer.echo("[pipeline] skipping review agents (--skip-review)", err=True)

    # Stage 6: OpenSpec review
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


def _run_review_agents(
    pr_result: PrResult,
    worktree_path: Path,
    max_turns: int,
    model: str | None,
    effort: str | None,
    max_budget_usd: float | None,
    permission_mode: str,
    verbose: bool,
    stages: list[StageResultUnion],
) -> bool:
    """Run review agents stage. Returns True if fix retry is needed."""
    assert pr_result.pr_url is not None
    # Extract PR number from URL (e.g., https://github.com/org/repo/pull/123)
    pr_number = int(pr_result.pr_url.rstrip("/").split("/")[-1])

    typer.echo(f"[pipeline] running review agents for PR #{pr_number}", err=True)

    review_results = dispatch_review_agents(
        pr_number=pr_number,
        worktree_path=worktree_path,
        max_turns=max_turns,
        model=model,
        effort=effort,
        max_budget_usd=max_budget_usd,
        permission_mode=permission_mode,
        verbose=verbose,
    )

    for result in review_results:
        stages.append(result)

    _post_review_comment(worktree_path, pr_result.pr_url, review_results, verbose)

    needs_fix = triage_findings(review_results)
    if needs_fix:
        typer.echo("[pipeline] high/critical findings detected, fix retry needed", err=True)
    else:
        typer.echo("[pipeline] no high/critical findings, proceeding", err=True)

    return needs_fix


def _post_review_comment(
    worktree_path: Path,
    pr_url: str,
    review_results: list[ReviewResult],
    verbose: bool,
) -> None:
    """Post a PR comment summarizing review agent findings."""
    total_findings = sum(len(r.findings) for r in review_results)

    if total_findings == 0:
        body = "All review agents passed with no findings."
    else:
        lines = ["## Review Agent Findings", ""]
        for result in review_results:
            if not result.findings:
                continue
            lines.append(f"### {result.agent_name}")
            for f in result.findings:
                location = f.file
                if f.line is not None:
                    location += f":{f.line}"
                lines.append(f"- **[{f.severity.upper()}]** {f.title} (`{location}`)")
                lines.append(f"  {f.description}")
            lines.append("")
        body = "\n".join(lines)

    try:
        gh_result = subprocess.run(
            ["gh", "pr", "comment", pr_url, "--body", body],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if gh_result.returncode != 0:
            typer.echo(
                f"[pipeline] warning: gh pr comment failed: {gh_result.stderr.strip()}",
                err=True,
            )
        elif verbose:
            typer.echo("[pipeline] posted review comment on PR", err=True)
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[pipeline] warning: gh pr comment failed: {e}", err=True)


def _run_review_fix_retry(
    change_name: str,
    pr_result: PrResult,
    worktree_path: Path,
    repo: Path,
    max_turns: int,
    model: str | None,
    effort: str | None,
    max_budget_usd: float | None,
    permission_mode: str,
    verbose: bool,
    stages: list[StageResultUnion],
) -> bool:
    """Re-dispatch worker with review feedback, re-run eval, push if passing.

    Returns True if fix succeeded (eval passed), False otherwise.
    """
    typer.echo("[pipeline] starting review fix retry", err=True)

    # Collect review results from stages
    review_results = [s for s in stages if isinstance(s, ReviewResult)]
    feedback = format_review_feedback(review_results)

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
        typer.echo(f"[pipeline] review fix worker failed: {worker_result.error}", err=True)
        return False

    eval_result = run_eval(worktree_path, verbose=verbose)
    stages.append(eval_result)

    if not eval_result.success:
        typer.echo(f"[pipeline] review fix eval failed: {eval_result.error}", err=True)
        return False

    # Push new commits to the PR branch
    try:
        push_result = subprocess.run(
            ["git", "push", "origin", "HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if push_result.returncode != 0:
            typer.echo(
                f"[pipeline] warning: git push failed: {push_result.stderr.strip()}",
                err=True,
            )
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[pipeline] warning: git push failed: {e}", err=True)

    # Post comment noting fixes
    assert pr_result.pr_url is not None
    comment = "Review findings addressed. New commits pushed to this branch."
    try:
        subprocess.run(
            ["gh", "pr", "comment", pr_result.pr_url, "--body", comment],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError):
        pass  # Non-critical

    typer.echo("[pipeline] review fix retry completed successfully", err=True)
    return True


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
