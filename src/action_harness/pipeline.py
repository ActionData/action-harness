"""End-to-end pipeline wiring."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import typer

from action_harness.evaluator import run_eval
from action_harness.event_log import EventLogger
from action_harness.merge import check_merge_gates, merge_pr, post_merge_blocked_comment
from action_harness.merge import wait_for_ci as wait_for_ci_checks
from action_harness.models import (
    AcknowledgedFinding,
    EvalResult,
    MergeResult,
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
from action_harness.profiler import BOOTSTRAP_EVAL_COMMANDS, RepoProfile, profile_repo
from action_harness.progress import write_progress
from action_harness.protection import (
    check_protected_files,
    flag_pr_protected,
    get_changed_files,
    load_protected_patterns,
)
from action_harness.review_agents import (
    dispatch_review_agents,
    filter_actionable_findings,
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
    profile: RepoProfile | None = None,
    protected_files: list[str] | None = None,
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

    # Check if any OpenSpecReviewResult has human tasks remaining
    needs_human = any(
        isinstance(stage, OpenSpecReviewResult) and stage.human_tasks_remaining > 0
        for stage in stages
    )

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
        needs_human=needs_human,
        protected_files=protected_files or [],
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
    harness_home: Path | None = None,
    repo_name: str | None = None,
    skip_review: bool = False,
    auto_merge: bool = False,
    wait_for_ci: bool = False,
    prompt: str | None = None,
    issue_number: int | None = None,
    review_cycle: list[str] | None = None,
) -> tuple[PrResult, RunManifest]:
    """Run the full pipeline: worktree -> worker -> eval -> retry -> PR.

    Returns a (PrResult, RunManifest) tuple. The manifest is always written
    to disk, on both success and failure.
    Cleans up worktree on terminal failure (preserves branch for inspection).

    When harness_home and repo_name are both set, workspaces are created at
    harness_home/workspaces/<repo_name>/<change_name>/ instead of /tmp.
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

    # Compute workspace path for managed repos
    workspace_dir: Path | None = None
    if harness_home is not None and repo_name is not None:
        workspace_dir = harness_home / "workspaces" / repo_name / change_name

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

    protected_files: list[str] = []

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
            workspace_dir=workspace_dir,
            skip_review=skip_review,
            protected_files_out=protected_files,
            auto_merge=auto_merge,
            wait_for_ci=wait_for_ci,
            prompt=prompt,
            issue_number=issue_number,
            review_cycle=review_cycle if review_cycle is not None else ["low", "med", "high"],
        )
    except Exception as e:
        typer.echo(f"[pipeline] unexpected error: {e}", err=True)
        logger.emit("pipeline.error", error=str(e))
        pr_result = PrResult(
            success=False, stage="pipeline", error=f"Unexpected error: {e}", branch=""
        )
    finally:
        # Label issue as failed if pipeline did not succeed (best-effort)
        if issue_number is not None and not pr_result.success:
            from action_harness.issue_intake import label_issue

            label_issue(issue_number, "harness:failed", repo)
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
        change_name,
        repo,
        started_at,
        stages,
        retries,
        pr_result,
        profile=profile,
        protected_files=protected_files,
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
    workspace_dir: Path | None = None,
    skip_review: bool = False,
    protected_files_out: list[str] | None = None,
    auto_merge: bool = False,
    wait_for_ci: bool = False,
    prompt: str | None = None,
    issue_number: int | None = None,
    review_cycle: list[str] | None = None,
) -> PrResult:
    """Inner pipeline logic. Appends to stages list as side effect.

    Separated so that run_pipeline can always build and write the manifest
    after this returns, regardless of which exit path is taken.
    """
    # Stage 1: Create worktree
    wt_result = create_worktree(change_name, repo, verbose=verbose, workspace_dir=workspace_dir)
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

    # Label issue as in-progress (best-effort)
    if issue_number is not None:
        from action_harness.issue_intake import comment_on_issue, label_issue

        label_issue(issue_number, "harness:in-progress", repo, verbose=verbose)

    # Stage 2+3: Worker dispatch + eval with retry loop
    attempt = 0
    feedback: str | None = None
    resume_session_id: str | None = None
    prior_worker_result: WorkerResult | None = None
    eval_result: EvalResult | None = None

    while attempt <= max_retries:
        # Pre-work eval on retries: if the prior worker produced commits,
        # run eval first — the commits may have already fixed the issue.
        if (
            attempt > 0
            and prior_worker_result is not None
            and prior_worker_result.commits_ahead > 0
        ):
            typer.echo("[pipeline] running pre-work eval before retry", err=True)
            pre_work_eval = run_eval(
                worktree_path, eval_commands=eval_commands, verbose=verbose, logger=logger
            )
            logger.emit(
                "eval.pre_work",
                stage="eval",
                success=pre_work_eval.success,
                commands_passed=pre_work_eval.commands_passed,
                commands_run=pre_work_eval.commands_run,
            )
            if pre_work_eval.success:
                typer.echo("[pipeline] pre-work eval passed, skipping retry", err=True)
                eval_result = pre_work_eval
                # Use prior worker result for PR metadata. If the worker
                # reported failure (e.g. zero-commit detection glitch) but
                # actually produced valid commits, mark it successful so
                # downstream consumers (manifest, PR body) aren't misled.
                if not prior_worker_result.success:
                    prior_worker_result = prior_worker_result.model_copy(
                        update={"success": True, "error": None}
                    )
                worker_result = prior_worker_result
                break
            # Pre-work eval failed — use its feedback if available (fresher than stale)
            feedback = pre_work_eval.feedback_prompt or feedback

        # Dispatch worker
        if feedback:
            typer.echo(f"[pipeline] retry {attempt}/{max_retries} with feedback", err=True)

        logger.emit(
            "worker.dispatched",
            stage="worker",
            attempt=attempt,
            session_id=resume_session_id,
            resumed=resume_session_id is not None,
        )

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
            session_id=resume_session_id,
            prompt=prompt,
        )
        stages.append(worker_result)

        if not worker_result.success:
            # Resume fallback: if we were resuming and it failed, try fresh dispatch
            # in the same iteration without incrementing attempt
            if resume_session_id is not None:
                typer.echo(
                    "[pipeline] session resume failed, retrying with fresh dispatch",
                    err=True,
                )
                logger.emit(
                    "worker.resume_fallback",
                    stage="worker",
                    session_id=resume_session_id,
                )
                resume_session_id = None
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
                    session_id=None,
                    prompt=prompt,
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
                prior_worker_result = worker_result
                attempt += 1
                feedback = worker_result.error
                resume_session_id = None
                continue

        logger.emit(
            "worker.completed",
            stage="worker",
            duration_seconds=worker_result.duration_seconds,
            success=True,
            commits_ahead=worker_result.commits_ahead,
            cost_usd=worker_result.cost_usd,
            session_id=worker_result.session_id,
            context_usage_pct=worker_result.context_usage_pct,
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

        # Eval failed — decide whether to resume or fresh dispatch on retry
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

        # Determine resume eligibility for next retry
        ctx_pct = worker_result.context_usage_pct
        if ctx_pct is not None and ctx_pct < 0.6 and worker_result.session_id is not None:
            resume_session_id = worker_result.session_id
            typer.echo(
                f"[pipeline] resuming session {resume_session_id} (context {ctx_pct:.0%})",
                err=True,
            )
        else:
            resume_session_id = None
            if ctx_pct is not None and ctx_pct >= 0.6:
                typer.echo(
                    f"[pipeline] context usage {ctx_pct:.0%} exceeds threshold, "
                    f"using fresh dispatch",
                    err=True,
                )

        # Write progress file for retry context (eval failed, retry will follow)
        write_progress(worktree_path, attempt + 1, worker_result, eval_result)

        logger.emit(
            "retry.scheduled",
            attempt=attempt + 1,
            reason="eval_failed",
            max_retries=max_retries,
            resume_session_id=resume_session_id,
        )
        prior_worker_result = worker_result
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
        prompt=prompt,
        issue_number=issue_number,
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

    # Label issue with PR-created status and comment with PR URL (best-effort)
    if issue_number is not None:
        label_issue(issue_number, "harness:pr-created", repo, verbose=verbose)
        if pr_result.pr_url:
            comment_on_issue(issue_number, f"PR created: {pr_result.pr_url}", repo, verbose=verbose)

    # Stage 4.5: Protected paths check
    patterns = load_protected_patterns(repo)
    if patterns:
        changed = get_changed_files(worktree_path, base_branch)
        protected_files = check_protected_files(changed, patterns)
    else:
        protected_files = []

    if protected_files_out is not None:
        protected_files_out.extend(protected_files)

    if protected_files and pr_result.pr_url:
        flag_pr_protected(pr_result.pr_url, protected_files, worktree_path, verbose)

    logger.emit(
        "protection.checked",
        stage="protection",
        protected_files=protected_files,
        patterns_count=len(patterns),
    )

    # Stage 5: Review agents (parallel code review) with fix-retry loop
    cycle = review_cycle if review_cycle is not None else ["low", "med", "high"]
    total_rounds = len(cycle)
    findings_remain = False
    if not skip_review:
        latest_review_results: list[ReviewResult] = []
        last_fix_succeeded = False
        acknowledged: list[AcknowledgedFinding] = []
        rounds_attempted = 0

        for round_idx, tolerance in enumerate(cycle):
            rounds_attempted = round_idx + 1
            typer.echo(
                f"[pipeline] review round {rounds_attempted}/{total_rounds} "
                f"(tolerance: {tolerance})",
                err=True,
            )
            _needs_any, latest_review_results = _run_review_agents(
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

            needs_fix = triage_findings(latest_review_results, tolerance)

            if not needs_fix:
                # Short-circuit: zero actionable findings at this tolerance
                findings_remain = False
                # Still post all findings to PR for visibility
                if pr_result.pr_url:
                    _post_review_comment(
                        worktree_path,
                        pr_result.pr_url,
                        latest_review_results,
                        verbose,
                        header=(
                            f"Review round {rounds_attempted}/{total_rounds} "
                            f"(tolerance: {tolerance})"
                        ),
                    )
                typer.echo(
                    f"[pipeline] no actionable findings at tolerance '{tolerance}', "
                    f"skipping remaining rounds",
                    err=True,
                )
                break

            findings_remain = True
            pre_fix_actionable = filter_actionable_findings(latest_review_results, tolerance)

            # Post review comment with ALL findings (unfiltered) for visibility
            if pr_result.pr_url:
                _post_review_comment(
                    worktree_path,
                    pr_result.pr_url,
                    latest_review_results,
                    verbose,
                    header=(
                        f"Review round {rounds_attempted}/{total_rounds} (tolerance: {tolerance})"
                    ),
                )

            last_fix_succeeded = _run_review_fix_retry(
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
                eval_commands=eval_commands,
                logger=logger,
                review_results=latest_review_results,
                tolerance=tolerance,
                prior_acknowledged=acknowledged if acknowledged else None,
                prompt=prompt,
            )
            if not last_fix_succeeded:
                typer.echo("[pipeline] review fix-retry failed", err=True)
                break

            # Track acknowledged findings: re-run review to see what persisted
            # We check in the next round's review anyway, so just track for now.
            # Match pre-fix actionable findings against next round's results.
            # For intermediate tracking, we note all pre-fix actionable as
            # potentially acknowledged — the next round will confirm via matching.
            for finding in pre_fix_actionable:
                # Only add if not already tracked
                already_tracked = any(
                    af.finding.file == finding.file and af.finding.title == finding.title
                    for af in acknowledged
                )
                if not already_tracked:
                    acknowledged.append(
                        AcknowledgedFinding(
                            finding=finding,
                            acknowledged_in_round=rounds_attempted,
                        )
                    )

        # After the loop, if findings were detected but the last fix-retry
        # succeeded, run a final verification review to check whether the
        # fix actually resolved them.
        if findings_remain and last_fix_succeeded:
            last_tolerance = cycle[-1]
            typer.echo("[pipeline] running verification review", err=True)
            _still_needs_any, latest_review_results = _run_review_agents(
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
            still_needs_fix = triage_findings(latest_review_results, last_tolerance)
            if not still_needs_fix:
                findings_remain = False

        if findings_remain and pr_result.pr_url:
            _post_review_comment(
                worktree_path,
                pr_result.pr_url,
                latest_review_results,
                verbose,
                header=f"Remaining findings after {rounds_attempted} fix-retry round(s)",
            )
    else:
        typer.echo("[pipeline] skipping review agents (--skip-review)", err=True)

    # Stage 6: OpenSpec review (skipped in prompt mode — no OpenSpec artifacts)
    if prompt is not None:
        typer.echo("[pipeline] skipping openspec review (prompt mode)", err=True)
        review_result = None
    else:
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
        for openspec_finding in review_result.findings:
            typer.echo(f"  - {openspec_finding}", err=True)
        typer.echo("[pipeline] complete (failed)", err=True)
        return PrResult(
            success=False,
            stage="pipeline",
            error="OpenSpec review returned findings",
            branch=branch,
            pr_url=pr_result.pr_url,
        )

    # Stage 7: Auto-merge (optional)
    if auto_merge and not pr_result.pr_url:
        typer.echo("[pipeline] auto-merge: skipping, no PR URL available", err=True)
        stages.append(MergeResult(success=True, merged=False, merge_blocked_reason="no PR URL"))
        logger.emit(
            "merge.completed",
            stage="merge",
            merged=False,
            blocked_reason="no PR URL",
        )
    elif auto_merge and pr_result.pr_url:
        logger.emit("merge.started", stage="merge", wait_for_ci=wait_for_ci)
        openspec_review_passed = review_result is None or review_result.success
        gates, all_passed = check_merge_gates(
            protected_files, findings_remain, openspec_review_passed, skip_review
        )

        merge_result: MergeResult
        if all_passed:
            ci_passed: bool | None = None
            if wait_for_ci:
                typer.echo("[pipeline] auto-merge: waiting for CI", err=True)
                ci_passed = wait_for_ci_checks(pr_result.pr_url, worktree_path, verbose=verbose)

            if not wait_for_ci or ci_passed:
                typer.echo("[pipeline] auto-merge: all gates passed, merging PR", err=True)
                merge_result = merge_pr(pr_result.pr_url, worktree_path, verbose=verbose)
                merge_result = merge_result.model_copy(update={"ci_passed": ci_passed})
            else:
                reason = "CI checks failed"
                typer.echo(f"[pipeline] auto-merge blocked: {reason}", err=True)
                merge_result = MergeResult(
                    success=True,
                    merged=False,
                    merge_blocked_reason=reason,
                    ci_passed=ci_passed,
                )
                ci_gates = {**gates, "ci_passed": False}
                post_merge_blocked_comment(
                    pr_result.pr_url, worktree_path, ci_gates, verbose=verbose
                )
        else:
            failed_gates = [name for name, passed in gates.items() if not passed]
            reason = f"Gates failed: {', '.join(failed_gates)}"
            typer.echo(f"[pipeline] auto-merge blocked: {reason}", err=True)
            merge_result = MergeResult(success=True, merged=False, merge_blocked_reason=reason)
            post_merge_blocked_comment(pr_result.pr_url, worktree_path, gates, verbose=verbose)

        stages.append(merge_result)

        logger.emit(
            "merge.completed",
            stage="merge",
            gates=gates,
            merged=merge_result.merged,
            blocked_reason=merge_result.merge_blocked_reason,
            ci_passed=merge_result.ci_passed,
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
) -> tuple[bool, list[ReviewResult]]:
    """Run review agents stage. Returns (needs_fix, review_results)."""
    if pr_result.pr_url is None:
        typer.echo("[pipeline] error: PR URL is None, cannot proceed", err=True)
        return False, []
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

    needs_fix = triage_findings(review_results)
    if needs_fix:
        typer.echo("[pipeline] findings detected, fix retry needed", err=True)
    else:
        typer.echo("[pipeline] no findings, proceeding", err=True)

    return needs_fix, review_results


def _post_review_comment(
    worktree_path: Path,
    pr_url: str,
    review_results: list[ReviewResult],
    verbose: bool,
    header: str = "Review Agent Findings",
) -> None:
    """Post a PR comment summarizing all review agent findings (unfiltered).

    Includes severity label tags on each finding for visibility regardless
    of the current tolerance level.
    """
    total_findings = sum(len(r.findings) for r in review_results)

    if total_findings == 0:
        body = "All review agents passed with no findings."
    else:
        lines = [f"## {header}", ""]
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
    eval_commands: list[str] | None = None,
    logger: EventLogger | None = None,
    review_results: list[ReviewResult] | None = None,
    tolerance: str = "low",
    prior_acknowledged: list[AcknowledgedFinding] | None = None,
    prompt: str | None = None,
) -> bool:
    """Re-dispatch worker with review feedback, re-run eval, push if passing.

    Returns True if fix succeeded (eval passed), False otherwise.
    Accepts review_results directly to avoid picking up stale results from
    prior review rounds.
    """
    typer.echo("[pipeline] starting review fix retry", err=True)

    if review_results is None:
        msg = "review_results is required"
        raise ValueError(msg)
    feedback = format_review_feedback(
        review_results, tolerance=tolerance, prior_acknowledged=prior_acknowledged
    )

    # Find session_id from the last successful WorkerResult for resume
    # Also check context_usage_pct — skip resume if context is exhausted
    fix_session_id: str | None = None
    for stage in reversed(stages):
        if isinstance(stage, WorkerResult) and stage.success:
            ctx_pct = stage.context_usage_pct
            if ctx_pct is not None and ctx_pct >= 0.6:
                typer.echo(
                    f"[pipeline] review fix-retry: context usage {ctx_pct:.0%} "
                    f"exceeds threshold, using fresh dispatch",
                    err=True,
                )
            else:
                fix_session_id = stage.session_id
            break

    if fix_session_id is not None:
        typer.echo(
            f"[pipeline] review fix-retry resuming session {fix_session_id}",
            err=True,
        )

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
        session_id=fix_session_id,
        prompt=prompt,
    )
    stages.append(worker_result)

    if not worker_result.success:
        # Resume fallback: if we tried to resume and it failed, try fresh
        if fix_session_id is not None:
            typer.echo(
                "[pipeline] review fix session resume failed, retrying fresh",
                err=True,
            )
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
                session_id=None,
                prompt=prompt,
            )
            stages.append(worker_result)

    if not worker_result.success:
        typer.echo(f"[pipeline] review fix worker failed: {worker_result.error}", err=True)
        return False

    eval_result = run_eval(
        worktree_path, eval_commands=eval_commands, verbose=verbose, logger=logger
    )
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
            return False
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[pipeline] warning: git push failed: {e}", err=True)
        return False

    # Post comment noting fixes (only if push succeeded)
    if pr_result.pr_url is None:
        typer.echo("[pipeline] error: PR URL is None, cannot proceed", err=True)
        return False
    comment = "Review findings addressed. New commits pushed to this branch."
    try:
        subprocess.run(
            ["gh", "pr", "comment", pr_result.pr_url, "--body", comment],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[pipeline] warning: gh pr comment failed: {e}", err=True)

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

    # Handle needs-human: post PR comment and add label
    if review_result.success and review_result.human_tasks_remaining > 0 and pr_result.pr_url:
        _flag_pr_needs_human(worktree_path, pr_result.pr_url, review_result.findings, verbose)

    if review_result.success and review_result.archived:
        pushed, push_error = push_archive_if_needed(
            worktree_path, base_branch, commits_before, verbose=verbose
        )
        if push_error:
            typer.echo(f"[pipeline] failed to push archive: {push_error}", err=True)
            review_result = review_result.model_copy(
                update={
                    "success": False,
                    "error": push_error,
                    "human_tasks_remaining": review_result.human_tasks_remaining,
                }
            )
        elif pushed and pr_result.pr_url:
            # Add a comment on the PR noting the archive was completed
            _comment_archive_complete(worktree_path, pr_result.pr_url, verbose)

    return review_result


def _flag_pr_needs_human(
    worktree_path: Path,
    pr_url: str,
    findings: list[str],
    verbose: bool,
) -> None:
    """Post a PR comment listing remaining human tasks and add a needs-human label."""
    # Build comment body — only include findings that describe human tasks
    human_findings = [f for f in findings if "human" in f.lower()]
    lines = ["## Human Tasks Remaining", ""]
    for finding in human_findings:
        lines.append(f"- {finding}")
    if not human_findings:
        lines.append("Human tasks remain incomplete. Check tasks.md for details.")
    body = "\n".join(lines)

    # Post comment
    try:
        result = subprocess.run(
            ["gh", "pr", "comment", pr_url, "--body", body],
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
            typer.echo("[pipeline] posted needs-human comment on PR", err=True)
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[pipeline] warning: gh pr comment failed: {e}", err=True)

    # Add label
    try:
        result = subprocess.run(
            ["gh", "pr", "edit", pr_url, "--add-label", "needs-human"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            typer.echo(
                f"[pipeline] warning: gh pr edit --add-label failed: {result.stderr.strip()}",
                err=True,
            )
        elif verbose:
            typer.echo("[pipeline] added needs-human label to PR", err=True)
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[pipeline] warning: gh pr edit --add-label failed: {e}", err=True)


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
