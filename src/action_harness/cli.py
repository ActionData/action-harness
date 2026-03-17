"""CLI entrypoint for action-harness."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import click
import typer

if TYPE_CHECKING:
    from action_harness.reporting import RunReport

from action_harness import __version__
from action_harness.models import (
    RepoDetail,
    RepoRoadmap,
    RepoSummary,
    ValidationError,
    WorkspaceInfo,
)
from action_harness.profiler import profile_repo
from action_harness.review_agents import TOLERANCE_THRESHOLD
from action_harness.slugify import slugify_prompt

app = typer.Typer(
    name="action-harness",
    add_completion=False,
    rich_markup_mode="markdown",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"action-harness {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Autonomous engineering pipeline powered by Claude Code.

    Orchestrates Claude Code workers through: task intake, implementation
    in isolated worktrees, external evaluation, retry with structured
    feedback, and PR creation.

    Requires **claude** and **gh** CLIs in PATH.
    """


def _validate_common(repo: Path) -> None:
    """Shared validation: repo exists, is git repo, required CLIs in PATH."""
    if not repo.exists():
        raise ValidationError(f"Repository path does not exist: {repo}")

    if not (repo / ".git").exists():
        raise ValidationError(f"Not a git repository: {repo}")

    if shutil.which("claude") is None:
        raise ValidationError("claude CLI not found in PATH")

    if shutil.which("gh") is None:
        raise ValidationError("gh CLI not found in PATH")


def validate_inputs(change: str, repo: Path) -> None:
    """Validate CLI inputs before starting the pipeline.

    Checks:
    - repo path exists and is a git repo
    - openspec change directory exists in the repo
    - claude CLI is in PATH
    - gh CLI is in PATH
    """
    _validate_common(repo)

    changes_root = repo / "openspec" / "changes"
    change_dir = (changes_root / change).resolve()
    if not change_dir.is_relative_to(changes_root.resolve()):
        raise ValidationError(f"Invalid change name (path traversal): {change}")
    if not change_dir.exists():
        raise ValidationError(f"Change directory not found: {change_dir}")


def validate_inputs_prompt(repo: Path) -> None:
    """Validate CLI inputs for prompt mode (no OpenSpec change directory needed).

    Checks:
    - repo path exists and is a git repo
    - claude CLI is in PATH
    - gh CLI is in PATH
    """
    _validate_common(repo)


def _resolve_harness_home(harness_home: Path | None) -> Path:
    """Resolve harness home: CLI flag > HARNESS_HOME env var > ~/harness/."""
    if harness_home is not None:
        return harness_home.resolve()
    env_val = os.environ.get("HARNESS_HOME")
    if env_val:
        return Path(env_val).resolve()
    return Path.home() / "harness"


@app.command()
def run(
    change: str | None = typer.Option(
        None,
        help="OpenSpec change name to implement (mutually exclusive with --prompt and --issue)",
    ),
    prompt: str | None = typer.Option(
        None,
        help="Freeform task description sent directly to the worker "
        "(mutually exclusive with --change and --issue)",
    ),
    issue: int | None = typer.Option(
        None,
        help="GitHub issue number to dispatch (mutually exclusive with --change and --prompt)",
    ),
    repo: str = typer.Option(
        ...,
        help="Target repository: local path, owner/repo shorthand, or full GitHub URL",
    ),
    harness_home: Path | None = typer.Option(
        None,
        "--harness-home",
        help="Harness home directory (default: HARNESS_HOME env or ~/harness/)",
    ),
    max_retries: int = typer.Option(3, help="Maximum eval retry attempts"),
    max_turns: int = typer.Option(200, help="Maximum Claude Code turns per dispatch"),
    model: str | None = typer.Option(None, help="Claude model to use (e.g., opus, sonnet)"),
    effort: str | None = typer.Option(
        None,
        click_type=click.Choice(["low", "medium", "high", "max"]),
        help="Effort level",
    ),
    max_budget_usd: float | None = typer.Option(
        None, "--max-budget-usd", help="Maximum dollar spend per worker dispatch"
    ),
    permission_mode: str = typer.Option(
        "bypassPermissions",
        "--permission-mode",
        help="Claude Code permission mode for headless operation",
    ),
    verbose: bool = typer.Option(False, help="Show detailed subprocess output on stderr"),
    skip_review: bool = typer.Option(
        False,
        "--skip-review",
        help="Skip the review-agents stage (bug-hunter, test-reviewer, quality-reviewer)",
    ),
    auto_merge: bool = typer.Option(
        False,
        "--auto-merge",
        help="Automatically merge the PR when all quality gates pass",
    ),
    wait_for_ci: bool = typer.Option(
        False,
        "--wait-for-ci",
        help="Wait for CI status checks before merging (requires --auto-merge)",
    ),
    max_findings_per_retry: int = typer.Option(
        5,
        "--max-findings-per-retry",
        min=0,
        help="Maximum review findings sent to the fix-retry worker per round. "
        "Higher-priority findings are selected first. 0 means no cap.",
    ),
    review_cycle: str = typer.Option(
        "low,med,high",
        "--review-cycle",
        help="Comma-separated tolerance levels per review round. "
        "Each level: low (all severities), med (medium+), high (critical/high only). "
        "Default: low,med,high. Example: --review-cycle high (single strict-only round).",
    ),
    resume: str | None = typer.Option(
        None,
        "--resume",
        help='Resume from a checkpoint: "latest" or a specific run ID',
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print plan without executing"
    ),
) -> None:
    """Run the action-harness pipeline from an OpenSpec change, freeform prompt, or GitHub issue.

    Provide exactly one of `--change`, `--prompt`, or `--issue`:

    - `--change NAME` implements an OpenSpec change via opsx:apply. The change
      must exist at REPO/openspec/changes/NAME/.
    - `--prompt TEXT` sends a freeform task description directly to the worker.
      No OpenSpec artifacts are needed. The pipeline skips the OpenSpec review
      stage but still runs eval, retry, and review agents.
    - `--issue NUMBER` reads a GitHub issue, detects OpenSpec change references
      in the body, and dispatches as --change or --prompt accordingly. The PR
      links back to the issue for automatic closure on merge.

    In all modes, the pipeline creates an isolated worktree, dispatches a
    Claude Code worker, runs eval (pytest, ruff, mypy), retries with
    structured feedback on failure, and opens a PR for human review.

    Use `--max-findings-per-retry N` to cap how many review findings are
    sent to the fix-retry worker per round (default 5). Findings are
    prioritized by severity and cross-agent agreement; lower-priority
    findings are deferred to the next round.

    With `--auto-merge`, the pipeline merges the PR when all quality gates
    pass (eval clean, no protected files, review agents clean, OpenSpec
    review passed). Add `--wait-for-ci` to also wait for CI checks.

    Use `--resume latest` to resume from the most recent checkpoint for the
    given change, or `--resume <run-id>` to resume a specific run. If no
    checkpoint exists, the pipeline starts fresh with a warning.

    The `--repo` flag accepts a local path (e.g., `.` or `/abs/path`),
    GitHub shorthand (e.g., `owner/repo`), or a full URL
    (e.g., `https://github.com/owner/repo` or `git@github.com:owner/repo.git`).
    """
    # Mutual exclusion validation: exactly one of --change, --prompt, --issue
    provided = sum(x is not None for x in (change, prompt, issue))
    if provided > 1:
        typer.echo("Error: Specify only one of --change, --prompt, or --issue", err=True)
        raise typer.Exit(code=1)

    if provided == 0:
        typer.echo("Error: Specify one of --change, --prompt, or --issue", err=True)
        raise typer.Exit(code=1)

    if prompt is not None and not prompt.strip():
        typer.echo("Error: --prompt must not be empty", err=True)
        raise typer.Exit(code=1)

    if issue is not None and issue <= 0:
        typer.echo("Error: --issue must be a positive integer", err=True)
        raise typer.Exit(code=1)

    if wait_for_ci and not auto_merge:
        typer.echo("Error: --wait-for-ci requires --auto-merge", err=True)
        raise typer.Exit(code=1)

    # Validate --review-cycle
    valid_tolerances = set(TOLERANCE_THRESHOLD.keys())
    review_cycle_list = [t.strip() for t in review_cycle.split(",") if t.strip()]
    if not review_cycle_list:
        typer.echo(
            "Error: --review-cycle must not be empty. Valid values: low, med, high",
            err=True,
        )
        raise typer.Exit(code=1)
    for t in review_cycle_list:
        if t not in valid_tolerances:
            typer.echo(
                f"Error: invalid tolerance '{t}' in --review-cycle. Valid values: low, med, high",
                err=True,
            )
            raise typer.Exit(code=1)

    resolved_home = _resolve_harness_home(harness_home)

    # Resolve repo: local path or remote reference
    from action_harness.repo import resolve_repo

    try:
        resolved_repo, repo_name = resolve_repo(repo, resolved_home, verbose=verbose)
    except ValidationError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    # Resolve --issue into --change or --prompt mode
    if issue is not None:
        # Validate common prerequisites (git repo, claude, gh) before calling gh
        try:
            _validate_common(resolved_repo)
        except ValidationError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from None

        from action_harness.issue_intake import (
            build_issue_prompt,
            detect_openspec_change,
            read_issue,
        )

        try:
            issue_data = read_issue(issue, resolved_repo)
        except ValidationError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from None

        detected_change = detect_openspec_change(issue_data.body, resolved_repo)
        if detected_change is not None:
            change = detected_change
        else:
            prompt = build_issue_prompt(issue, issue_data.title, issue_data.body)

    # Compute task_label: either the change name or a prompt-derived slug
    if prompt is not None:
        slug = slugify_prompt(prompt)
        if not slug:
            if issue is not None:
                typer.echo(
                    "Error: issue title must contain at least one alphanumeric character",
                    err=True,
                )
            else:
                typer.echo(
                    "Error: --prompt must contain at least one alphanumeric character",
                    err=True,
                )
            raise typer.Exit(code=1)
        task_label = f"prompt-{slug}"
    else:
        if change is None:
            typer.echo("Error: specify one of --change, --prompt, or --issue", err=True)
            raise typer.Exit(code=1)
        task_label = change

    # Validate inputs: prompt mode skips OpenSpec directory check
    try:
        if prompt is not None:
            validate_inputs_prompt(resolved_repo)
        elif change is not None:
            validate_inputs(change, resolved_repo)
    except ValidationError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    # Determine if this is a managed repo (cloned to harness home)
    is_managed = _is_managed_repo(resolved_repo, resolved_home)

    if dry_run:
        profile = profile_repo(resolved_repo)
        if is_managed:
            workspace_path = str(resolved_home / "workspaces" / repo_name / task_label)
        else:
            workspace_path = f"/tmp/action-harness-*/{task_label}"
        if issue is not None:
            resolved_mode = "change" if change is not None else "prompt"
            typer.echo(f"Dry-run plan for issue #{issue} (resolved as {resolved_mode}):")
            if resolved_mode == "prompt":
                preview = (prompt or "")[:120]
                typer.echo(f"  prompt preview: {preview}")
            else:
                typer.echo(f"  change: {task_label}")
        elif prompt is not None:
            typer.echo(f"Dry-run plan for prompt: {prompt}")
        else:
            typer.echo(f"Dry-run plan for change '{task_label}':")
        typer.echo(f"  repo: {resolved_repo}")
        typer.echo(f"  worktree: {workspace_path}")
        typer.echo(f"  branch: harness/{task_label}")
        typer.echo(f"  worker: claude --output-format json --max-turns {max_turns}")
        typer.echo(f"  model: {model or 'default'}")
        typer.echo(f"  effort: {effort or 'default'}")
        typer.echo(f"  max-budget-usd: {max_budget_usd if max_budget_usd is not None else 'none'}")
        typer.echo(f"  permission-mode: {permission_mode}")
        typer.echo(f"  ecosystem: {profile.ecosystem}")
        typer.echo(f"  profile source: {profile.source}")
        typer.echo("  eval commands:")
        for cmd in profile.eval_commands:
            typer.echo(f"    - {cmd}")
        typer.echo(f"  max-findings-per-retry: {max_findings_per_retry}")
        cycle_str = ",".join(review_cycle_list)
        typer.echo(f"  review-cycle: {cycle_str} ({len(review_cycle_list)} round(s))")
        typer.echo(f"  pr title: [harness] {task_label}")
        typer.echo(f"  auto-merge: {'enabled' if auto_merge else 'disabled'}")
        typer.echo(f"  wait-for-ci: {'enabled' if wait_for_ci else 'disabled'}")
        typer.echo(f"  max retries: {max_retries}")
        if resume is not None:
            typer.echo(f"  resume: {resume}")
        raise typer.Exit(code=0)

    # Resolve --resume checkpoint
    from action_harness.models import PipelineCheckpoint

    resolved_checkpoint: PipelineCheckpoint | None = None
    if resume is not None:
        from action_harness.checkpoint import find_latest_checkpoint, read_checkpoint

        if resume == "latest":
            resolved_checkpoint = find_latest_checkpoint(resolved_repo, task_label)
        else:
            resolved_checkpoint = read_checkpoint(resolved_repo, resume)

        if resolved_checkpoint is None:
            typer.echo(
                f"[resume] no checkpoint found for '{resume}', starting fresh",
                err=True,
            )

    from action_harness.pipeline import run_pipeline

    pr_result, manifest = run_pipeline(
        change_name=task_label,
        repo=resolved_repo,
        max_retries=max_retries,
        max_turns=max_turns,
        model=model,
        effort=effort,
        max_budget_usd=max_budget_usd,
        permission_mode=permission_mode,
        verbose=verbose,
        harness_home=resolved_home if is_managed else None,
        repo_name=repo_name if is_managed else None,
        skip_review=skip_review,
        auto_merge=auto_merge,
        wait_for_ci=wait_for_ci,
        prompt=prompt,
        issue_number=issue,
        review_cycle=review_cycle_list,
        max_findings_per_retry=max_findings_per_retry,
        checkpoint=resolved_checkpoint,
    )

    if manifest.manifest_path:
        typer.echo(f"[pipeline] manifest saved to {manifest.manifest_path}", err=True)

    if not pr_result.success:
        raise typer.Exit(code=1)


def _is_managed_repo(repo_path: Path, harness_home: Path) -> bool:
    """Check if a repo path is under harness_home/repos/ (i.e., managed)."""
    try:
        repo_path.resolve().relative_to(harness_home.resolve() / "repos")
        return True
    except ValueError:
        return False


@app.command()
def clean(
    repo: str | None = typer.Option(None, help="Repo to clean workspaces for (owner/repo or path)"),
    change: str | None = typer.Option(None, help="Specific change workspace to clean"),
    all_workspaces: bool = typer.Option(False, "--all", help="Remove all workspaces"),
    harness_home: Path | None = typer.Option(
        None,
        "--harness-home",
        help="Harness home directory (default: HARNESS_HOME env or ~/harness/)",
    ),
) -> None:
    """Remove workspaces (worktrees) created by the harness.

    Removes workspace directories and prunes git worktrees. Does NOT
    remove cloned repos.

    Examples:

        action-harness clean --repo user/app --change fix-bug

        action-harness clean --repo user/app

        action-harness clean --all
    """
    if not all_workspaces and repo is None:
        typer.echo("Error: specify --repo or --all", err=True)
        raise typer.Exit(code=1)

    resolved_home = _resolve_harness_home(harness_home)
    workspaces_root = resolved_home / "workspaces"

    if not workspaces_root.exists():
        typer.echo("[clean] no workspaces directory found", err=True)
        raise typer.Exit(code=0)

    if all_workspaces:
        # Remove all workspaces
        _clean_all_workspaces(workspaces_root, resolved_home)
    elif repo is not None:
        # Resolve repo name
        from action_harness.repo import resolve_repo

        try:
            resolved_repo, repo_name = resolve_repo(repo, resolved_home)
        except ValidationError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from None

        repo_ws_dir = workspaces_root / repo_name
        if not repo_ws_dir.exists():
            typer.echo(f"[clean] no workspaces found for {repo_name}", err=True)
            raise typer.Exit(code=0)

        if change is not None:
            # Clean specific workspace — guard against path traversal
            ws_path = (repo_ws_dir / change).resolve()
            if not ws_path.is_relative_to(repo_ws_dir.resolve()):
                typer.echo(f"Error: invalid change name (path traversal): {change}", err=True)
                raise typer.Exit(code=1) from None
            if ws_path.exists():
                _remove_workspace(ws_path, resolved_repo)
                typer.echo(f"[clean] removed workspace {repo_name}/{change}", err=True)
            else:
                typer.echo(f"[clean] workspace not found: {repo_name}/{change}", err=True)
        else:
            # Clean all workspaces for this repo
            for ws_path in sorted(repo_ws_dir.iterdir()):
                if ws_path.is_dir():
                    _remove_workspace(ws_path, resolved_repo)
                    typer.echo(
                        f"[clean] removed workspace {repo_name}/{ws_path.name}",
                        err=True,
                    )
            # Remove the repo workspace directory if empty
            if repo_ws_dir.exists() and not any(repo_ws_dir.iterdir()):
                repo_ws_dir.rmdir()

        # Prune worktrees in the repo clone
        _prune_worktrees(resolved_repo)


def _remove_workspace(ws_path: Path, repo_path: Path) -> None:
    """Remove a workspace directory and its git worktree reference."""
    # Try git worktree remove first
    result = subprocess.run(
        ["git", "worktree", "remove", "--force", str(ws_path)],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        typer.echo(
            f"[clean] warning: git worktree remove failed: {result.stderr.strip()}", err=True
        )
    # If directory still exists, force-remove it
    if ws_path.exists():
        shutil.rmtree(ws_path, ignore_errors=True)


def _prune_worktrees(repo_path: Path) -> None:
    """Run git worktree prune in the given repo."""
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    typer.echo(f"[clean] pruned worktrees in {repo_path}", err=True)


@app.command()
def assess(
    repo: Path = typer.Option(
        ...,
        help="Path to the repository to assess",
    ),
    deep: bool = typer.Option(
        False,
        "--deep",
        help="Run agent-based quality assessment in addition to mechanical scan",
    ),
    propose: bool = typer.Option(
        False,
        "--propose",
        help="Generate OpenSpec proposals for identified gaps (implies --deep)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output full AssessmentReport JSON to stdout",
    ),
) -> None:
    """Assess a repository's readiness for autonomous agent work.

    Scores six categories: CI guardrails, testability, context, tooling,
    observability, and isolation. Each scores 0-100 based on mechanical
    signals (file presence, config parsing, CI workflow analysis).

    Modes:

    - **Base** (default): mechanical scan only — fast, no LLM cost.
    - **--deep**: adds a read-only assessment agent for quality judgment.
    - **--propose**: generates OpenSpec change proposals for gaps (implies --deep).

    The `--json` flag outputs the full report as JSON to stdout. All
    diagnostic output goes to stderr.

    Examples:

        action-harness assess --repo .

        action-harness assess --repo ./my-project --json

        action-harness assess --repo . --deep --propose
    """
    from datetime import UTC, datetime
    from typing import Literal

    from action_harness.assessment import AssessmentReport
    from action_harness.branch_protection import check_branch_protection
    from action_harness.ci_parser import parse_github_actions
    from action_harness.formatter import collect_proposals, print_report
    from action_harness.scanner import (
        analyze_test_structure,
        detect_context_signals,
        detect_isolation_signals,
        detect_observability_signals,
        detect_tooling_signals,
    )
    from action_harness.scoring import compute_overall, score_all_categories

    # --propose implies --deep
    if propose:
        deep = True

    # Determine mode
    mode: Literal["base", "deep", "propose"]
    if propose:
        mode = "propose"
    elif deep:
        mode = "deep"
    else:
        mode = "base"

    repo = repo.resolve()
    if not repo.exists():
        typer.echo(f"Error: repository path does not exist: {repo}", err=True)
        raise typer.Exit(code=1)

    if not (repo / ".git").exists():
        typer.echo(f"Error: not a git repository: {repo}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"[assess] starting {mode} assessment of {repo}", err=True)

    # Step 1: Profile repo for ecosystem
    profile = profile_repo(repo)
    typer.echo(f"[assess] ecosystem: {profile.ecosystem}", err=True)

    # Step 2: Run all mechanical scanners
    bp = check_branch_protection(repo)
    ci_signals = parse_github_actions(repo, branch_protection=bp)

    testability_signals = analyze_test_structure(repo, profile.ecosystem)
    context_signals = detect_context_signals(repo)
    tooling_signals = detect_tooling_signals(repo)
    observability_signals = detect_observability_signals(repo)
    isolation_signals = detect_isolation_signals(repo)

    # Step 3: Score all categories
    categories = score_all_categories(
        ci_signals=ci_signals,
        testability_signals=testability_signals,
        context_signals=context_signals,
        tooling_signals=tooling_signals,
        observability_signals=observability_signals,
        isolation_signals=isolation_signals,
    )

    # Step 4: Deep mode — agent assessment
    if deep:
        typer.echo("[assess] running agent assessment (--deep)", err=True)
        from action_harness.assess_agent import run_agent_assessment

        categories = run_agent_assessment(categories, repo)

    # Step 5: Build report
    overall = compute_overall(categories)
    proposals = collect_proposals(categories)

    report = AssessmentReport(
        overall_score=overall,
        categories=categories,
        proposals=proposals,
        repo_path=str(repo),
        timestamp=datetime.now(UTC).isoformat(),
        mode=mode,
    )

    # Step 6: Propose mode — generate OpenSpec proposals
    if propose and proposals:
        typer.echo("[assess] generating proposals (--propose)", err=True)
        from action_harness.gap_proposals import generate_proposals

        generate_proposals(proposals, repo, profile)

    # Step 7: Output
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        print_report(report, deep=deep, propose=propose)

    typer.echo(f"[assess] complete: overall score = {overall}", err=True)


def _clean_all_workspaces(workspaces_root: Path, harness_home: Path) -> None:
    """Remove all workspaces across all repos."""
    repos_dir = harness_home / "repos"
    for repo_dir in sorted(workspaces_root.iterdir()):
        if not repo_dir.is_dir():
            continue
        # Find the corresponding clone for worktree pruning
        clone_dir = repos_dir / repo_dir.name if repos_dir.exists() else None
        for ws_path in sorted(repo_dir.iterdir()):
            if ws_path.is_dir():
                if clone_dir and clone_dir.exists():
                    _remove_workspace(ws_path, clone_dir)
                else:
                    shutil.rmtree(ws_path, ignore_errors=True)
                typer.echo(
                    f"[clean] removed workspace {repo_dir.name}/{ws_path.name}",
                    err=True,
                )
        # Remove the repo workspace directory if empty
        if repo_dir.exists() and not any(repo_dir.iterdir()):
            repo_dir.rmdir()
        # Prune worktrees if clone exists
        if clone_dir and clone_dir.exists():
            _prune_worktrees(clone_dir)
    typer.echo("[clean] all workspaces removed", err=True)


@app.command()
def report(
    repo: Path = typer.Option(
        ...,
        help="Path to the repository to report on",
    ),
    since: str | None = typer.Option(
        None,
        "--since",
        help="Filter runs: relative (7d, 24h) or absolute (2026-03-15)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output full report JSON to stdout",
    ),
    harness_home: Path | None = typer.Option(
        None,
        "--harness-home",
        help="Harness home directory (default: HARNESS_HOME env or ~/harness/)",
    ),
) -> None:
    """Aggregate run manifests into a failure report.

    Reads all run manifests from `.action-harness/runs/` in the target
    repo and produces an aggregate report with success rates, failure
    stage distribution, recurring review findings, catalog rule frequency,
    and cost/duration trends.

    Use `--since` to limit the report window (e.g., `--since 7d` for the
    last 7 days, `--since 2026-03-15` for runs since a specific date).

    Use `--json` for machine-readable output to stdout. All diagnostic
    output goes to stderr.

    Examples:

        action-harness report --repo .

        action-harness report --repo . --since 30d

        action-harness report --repo . --json
    """
    import json as json_mod

    from action_harness.reporting import aggregate_report, load_manifests

    repo = repo.resolve()
    if not repo.exists():
        typer.echo(f"Error: repository path does not exist: {repo}", err=True)
        raise typer.Exit(code=1)
    if not (repo / ".git").exists():
        typer.echo(f"Error: not a git repository: {repo}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"[report] starting report for {repo}", err=True)

    # Load manifests
    manifests = load_manifests(repo, since=since)
    if not manifests:
        if json_output:
            typer.echo('{"error": "No runs found"}')
        else:
            typer.echo("No runs found.")
        return

    # Load catalog frequency from harness home
    catalog_frequency: dict[str, int] | None = None
    resolved_home = _resolve_harness_home(harness_home)
    # For local repos, repo.name is the directory name. For managed repos
    # (cloned to harness_home/repos/), the directory name matches what
    # resolve_repo produced. This won't find catalog data if the user passes
    # a local path that differs from the managed repo directory name — that's
    # acceptable since catalog frequency is best-effort context, not required.
    repo_name = repo.name
    freq_path = resolved_home / "repos" / repo_name / "knowledge" / "findings-frequency.json"
    typer.echo(f"[report] checking catalog frequency at {freq_path}", err=True)

    if freq_path.is_file():
        try:
            raw = freq_path.read_text(encoding="utf-8")
            freq_data = json_mod.loads(raw)
            # Nested structure: {entry_id: {"count": int, "last_seen": str}}
            catalog_frequency = {}
            for entry_id, entry in freq_data.items():
                if isinstance(entry, dict) and "count" in entry:
                    catalog_frequency[entry_id] = entry["count"]
            typer.echo(
                f"[report] loaded {len(catalog_frequency)} catalog entries",
                err=True,
            )
        except (OSError, UnicodeDecodeError, json_mod.JSONDecodeError) as e:
            typer.echo(f"[report] warning: could not read frequency data: {e}", err=True)
    else:
        typer.echo("[report] no catalog frequency data found", err=True)

    # Aggregate
    report_data = aggregate_report(manifests, catalog_frequency=catalog_frequency)

    if json_output:
        typer.echo(report_data.model_dump_json(indent=2))
    else:
        _print_report(report_data, since=since)

    typer.echo("[report] complete", err=True)


def _print_report(report_data: RunReport, since: str | None = None) -> None:
    """Format and print a human-readable report to stdout.

    The design doc shows a repo name in the header (``Harness Report — owner/repo``)
    and failure-stage annotations on recent runs. Both omitted here because the
    report command takes a local path, not an owner/repo identifier, and stage
    info isn't in RecentRunSummary. Acceptable for v1 — can be added if needed.
    """
    typer.echo("Harness Report")
    period = f"since {since}" if since else "all time"
    typer.echo(f"Period: {period} ({report_data.total_runs} runs)")
    typer.echo("")

    # Success rate
    typer.echo(
        f"Success Rate:  {report_data.successful_runs}/{report_data.total_runs} "
        f"({report_data.success_rate:.0f}%)"
    )

    # Cost
    if report_data.total_cost_usd is not None:
        typer.echo(f"Total Cost:    ${report_data.total_cost_usd:.2f}")
    else:
        typer.echo("Total Cost:    N/A")

    # Duration
    if report_data.avg_duration_seconds is not None:
        avg_min = report_data.avg_duration_seconds / 60.0
        typer.echo(f"Avg Duration:  {avg_min:.0f}m")
    else:
        typer.echo("Avg Duration:  N/A")

    typer.echo("")

    # Failure stages
    if report_data.failures_by_stage:
        typer.echo("Top Failure Stages:")
        for stage, count in sorted(
            report_data.failures_by_stage.items(), key=lambda x: x[1], reverse=True
        ):
            label = "failure" if count == 1 else "failures"
            typer.echo(f"  {stage}:  {count} {label}")
        typer.echo("")

    # Recurring findings
    if report_data.recurring_findings:
        typer.echo("Top Recurring Findings:")
        for finding in report_data.recurring_findings[:10]:
            typer.echo(f'  "{finding.title}" — {finding.count} run(s)')
        typer.echo("")

    # Catalog frequency
    if report_data.catalog_frequency:
        typer.echo("Catalog Rule Frequency:")
        sorted_freq = sorted(
            report_data.catalog_frequency.items(), key=lambda x: x[1], reverse=True
        )
        for entry_id, count in sorted_freq[:10]:
            typer.echo(f"  {entry_id}:  count={count}")
        typer.echo("")

    # Recent runs
    if report_data.recent_runs:
        typer.echo("Recent Runs:")
        for run in report_data.recent_runs:
            status = "✓" if run.success else "✗"
            cost_str = f"${run.cost_usd:.2f}" if run.cost_usd is not None else "N/A"
            dur_str = f"{run.duration_seconds / 60.0:.0f}m" if run.duration_seconds else "N/A"
            typer.echo(f"  {run.date} {run.change_name}  {status}  {cost_str}  {dur_str}")


# ── Dashboard: repos sub-app ─────────────────────────────────────────

repos_app = typer.Typer(name="repos", add_completion=False)
app.add_typer(repos_app, help="List and inspect onboarded repos.")


@repos_app.callback(invoke_without_command=True)
def repos_list(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    harness_home: Path | None = typer.Option(
        None,
        "--harness-home",
        help="Harness home directory (default: HARNESS_HOME env or ~/harness/)",
    ),
) -> None:
    """List all onboarded repos with summary info."""
    if ctx.invoked_subcommand is not None:
        return

    from action_harness.dashboard import list_repos

    resolved_home = _resolve_harness_home(harness_home)
    summaries = list_repos(resolved_home)

    if json_output:
        import json as json_mod

        typer.echo(json_mod.dumps([s.model_dump(mode="json") for s in summaries], indent=2))
        return

    _format_repos_list(summaries)


def _format_repos_list(summaries: list[RepoSummary]) -> None:
    """Formatted text output for repos list."""
    if not summaries:
        typer.echo("No repos onboarded.")
        return

    typer.echo("Onboarded Repos")
    typer.echo("═" * 60)

    # Compute max name length for alignment
    max_name = max(len(s.name) for s in summaries)

    for s in summaries:
        harness_mark = "✓" if s.has_harness_md else "✗"
        protected_mark = "✓" if s.has_protected_paths else "✗"
        completed_str = f", {s.completed_changes} completed" if s.completed_changes > 0 else ""
        typer.echo(
            f"  {s.name:<{max_name}}  "
            f"HARNESS.md: {harness_mark}  "
            f"Protected: {protected_mark}  "
            f"Workspaces: {s.workspace_count}  "
            f"Changes: {s.active_changes} active{completed_str}"
        )

    typer.echo("═" * 60)


@repos_app.command()
def show(
    name: str = typer.Argument(help="Repo name to show details for"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    harness_home: Path | None = typer.Option(
        None,
        "--harness-home",
        help="Harness home directory (default: HARNESS_HOME env or ~/harness/)",
    ),
) -> None:
    """Show detailed view of a single onboarded repo."""
    from action_harness.dashboard import repo_detail

    resolved_home = _resolve_harness_home(harness_home)

    # Check repo exists before calling
    repo_dir = resolved_home / "repos" / name
    if not repo_dir.is_dir():
        typer.echo(f"Repo '{name}' not found in {resolved_home}/repos/", err=True)
        raise typer.Exit(code=1)

    try:
        detail = repo_detail(resolved_home, name)
    except FileNotFoundError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from None

    if json_output:
        typer.echo(detail.model_dump_json(indent=2))
        return

    _format_repo_detail(detail)


def _format_repo_detail(detail: RepoDetail) -> None:
    """Formatted text output for repo detail."""
    typer.echo(f"Repo: {detail.summary.name}")
    typer.echo("═" * 60)

    # HARNESS.md section
    typer.echo("HARNESS.md")
    typer.echo("─" * 40)
    if detail.harness_md_content:
        typer.echo(detail.harness_md_content.rstrip())
    else:
        typer.echo("  Not configured")
    typer.echo("")

    # Protected Patterns section
    typer.echo("Protected Patterns")
    typer.echo("─" * 40)
    if detail.protected_patterns:
        for p in detail.protected_patterns:
            typer.echo(f"  • {p}")
    else:
        typer.echo("  None")
    typer.echo("")

    # Workspaces section
    typer.echo("Workspaces")
    typer.echo("─" * 40)
    if detail.workspaces:
        for ws in detail.workspaces:
            stale_mark = "  (stale)" if ws.stale else ""
            typer.echo(
                f"  {ws.change_name}  {ws.branch}  {ws.last_commit_age_days}d ago{stale_mark}"
            )
    else:
        typer.echo("  None")
    typer.echo("")

    # Roadmap section
    typer.echo("Roadmap")
    typer.echo("─" * 40)
    if detail.roadmap_content:
        typer.echo(detail.roadmap_content.rstrip())
    else:
        typer.echo("  No roadmap")
    typer.echo("")

    # OpenSpec Changes section
    active = detail.summary.active_changes
    completed = detail.completed_changes
    typer.echo(f"OpenSpec Changes ({active} active, {completed} completed)")
    typer.echo("─" * 40)
    if detail.openspec_changes:
        for c in detail.openspec_changes:
            bar = _progress_bar(c.progress_pct)
            typer.echo(f"  ◉ {c.name}  {bar} {c.progress_pct:.0f}%")
    else:
        typer.echo("  None")

    typer.echo("═" * 60)


def _progress_bar(pct: float, width: int = 20) -> str:
    """Render a progress bar like [████░░░░░░░░░░░░░░░░]."""
    clamped = max(0.0, min(100.0, pct))
    filled = int(width * clamped / 100.0)
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}]"


# ── Dashboard: workspaces command ────────────────────────────────────


@app.command()
def workspaces(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    harness_home: Path | None = typer.Option(
        None,
        "--harness-home",
        help="Harness home directory (default: HARNESS_HOME env or ~/harness/)",
    ),
) -> None:
    """List all workspaces across all repos with staleness info."""
    from action_harness.dashboard import list_workspaces

    resolved_home = _resolve_harness_home(harness_home)
    ws_list = list_workspaces(resolved_home)

    if json_output:
        import json as json_mod

        typer.echo(json_mod.dumps([w.model_dump(mode="json") for w in ws_list], indent=2))
        return

    _format_workspaces(ws_list)


def _format_workspaces(ws_list: list[WorkspaceInfo]) -> None:
    """Formatted text output for workspaces list."""
    if not ws_list:
        typer.echo("No workspaces found.")
        return

    typer.echo("Workspaces")
    typer.echo("═" * 60)

    # Group by repo
    current_repo = ""
    for ws in ws_list:
        if ws.repo_name != current_repo:
            current_repo = ws.repo_name
            typer.echo(current_repo)
        stale_mark = "  (stale)" if ws.stale else ""
        typer.echo(f"  {ws.change_name}  {ws.branch}  {ws.last_commit_age_days}d ago{stale_mark}")
    typer.echo("")
    typer.echo("═" * 60)


# ── Dashboard: roadmap command ───────────────────────────────────────


@app.command()
def roadmap(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    harness_home: Path | None = typer.Option(
        None,
        "--harness-home",
        help="Harness home directory (default: HARNESS_HOME env or ~/harness/)",
    ),
) -> None:
    """Cross-repo view of OpenSpec roadmaps and active changes."""
    from action_harness.dashboard import cross_repo_roadmap

    resolved_home = _resolve_harness_home(harness_home)
    roadmaps = cross_repo_roadmap(resolved_home)

    if json_output:
        import json as json_mod

        typer.echo(json_mod.dumps([r.model_dump(mode="json") for r in roadmaps], indent=2))
        return

    _format_roadmap(roadmaps)


def _format_roadmap(roadmaps: list[RepoRoadmap]) -> None:
    """Formatted text output for cross-repo roadmap."""
    if not roadmaps:
        typer.echo("No repos onboarded.")
        return

    typer.echo("Cross-Repo Roadmap")
    typer.echo("═" * 60)

    for rm in roadmaps:
        completed_str = f", {rm.completed_count} completed" if rm.completed_count > 0 else ""
        typer.echo(f"{rm.repo_name} ({len(rm.active_changes)} active{completed_str})")

        if not rm.active_changes and rm.roadmap_content is None:
            typer.echo("  No OpenSpec")
        elif not rm.active_changes:
            typer.echo("  No active changes")
        else:
            for c in rm.active_changes:
                indicator = "✓" if c.progress_pct >= 100.0 else "◉"
                bar = _progress_bar(c.progress_pct)
                typer.echo(f"  {indicator} {c.name}  {bar} {c.progress_pct:.0f}%")
        typer.echo("")

    typer.echo("═" * 60)


# ── Progress: live event feed ────────────────────────────────────────


@app.command()
def progress(
    repo: Path = typer.Option(
        ...,
        help="Path to the repository to follow",
    ),
    run: str | None = typer.Option(
        None,
        "--run",
        help="Follow a specific run ID instead of the latest",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output raw JSON events (one per line) instead of formatted text",
    ),
) -> None:
    """Follow live pipeline progress by tailing the event log.

    Tails the most recent `.events.jsonl` file and displays human-readable
    pipeline progress: stage names, elapsed time, worker status, eval
    results, review findings, and cost.

    Use `--run <run-id>` to follow a specific run instead of the latest.
    Use `--json` for machine-readable streaming output (one JSON event per
    line, suitable for piping to `jq`).

    Exits automatically when a `run.completed` or `pipeline.error` event
    is received.

    Examples:

        action-harness progress --repo .

        action-harness progress --repo . --run 2026-03-17T01-00-00-my-change

        action-harness progress --repo . --json
    """
    from datetime import datetime

    from action_harness.event_log import PipelineEvent
    from action_harness.progress_feed import (
        find_event_log_by_run_id,
        find_latest_event_log,
        format_event,
        tail_event_log,
    )

    repo = repo.resolve()
    if not repo.exists():
        typer.echo(f"Error: repository path does not exist: {repo}", err=True)
        raise typer.Exit(code=1)

    # Resolve the event log path
    if run is not None:
        log_path = find_event_log_by_run_id(repo, run)
        if log_path is None:
            typer.echo(f"Event log not found for run: {run}", err=True)
            raise typer.Exit(code=1)
    else:
        log_path = find_latest_event_log(repo)
        if log_path is None:
            typer.echo("No event logs found", err=True)
            raise typer.Exit(code=1)

    start_time: datetime | None = None
    saw_error = False

    def _on_event(event: PipelineEvent) -> bool:
        """Process each event: format and print, track start time."""
        nonlocal start_time, saw_error

        # Track start_time from run.started
        if event.event == "run.started" and start_time is None:
            start_time = datetime.fromisoformat(event.timestamp)

        if json_output:
            typer.echo(event.model_dump_json())
        else:
            formatted = format_event(event, start_time)
            typer.echo(formatted)

        # Exit on terminal events
        if event.event in ("run.completed", "pipeline.error"):
            if event.event == "pipeline.error":
                saw_error = True
            return False

        return True

    completed_normally = tail_event_log(log_path, _on_event)

    if saw_error or not completed_normally:
        raise typer.Exit(code=1)
