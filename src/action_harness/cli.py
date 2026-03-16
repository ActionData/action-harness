"""CLI entrypoint for action-harness."""

import os
import shutil
import subprocess
from pathlib import Path

import click
import typer

from action_harness import __version__
from action_harness.models import ValidationError
from action_harness.profiler import profile_repo
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
    review_cycle: str = typer.Option(
        "low,med,high",
        "--review-cycle",
        help="Comma-separated tolerance levels per review round. "
        "Each level: low (all severities), med (medium+), high (critical/high only). "
        "Default: low,med,high. Example: --review-cycle high (single strict-only round).",
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

    With `--auto-merge`, the pipeline merges the PR when all quality gates
    pass (eval clean, no protected files, review agents clean, OpenSpec
    review passed). Add `--wait-for-ci` to also wait for CI checks.

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
    from action_harness.review_agents import TOLERANCE_THRESHOLD

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
        cycle_str = ",".join(review_cycle_list)
        typer.echo(f"  review-cycle: {cycle_str} ({len(review_cycle_list)} round(s))")
        typer.echo(f"  pr title: [harness] {task_label}")
        typer.echo(f"  auto-merge: {'enabled' if auto_merge else 'disabled'}")
        typer.echo(f"  wait-for-ci: {'enabled' if wait_for_ci else 'disabled'}")
        typer.echo(f"  max retries: {max_retries}")
        raise typer.Exit(code=0)

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
