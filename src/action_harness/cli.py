"""CLI entrypoint for action-harness."""

import shutil
from pathlib import Path

import click
import typer

from action_harness import __version__
from action_harness.profiler import profile_repo

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


class ValidationError(Exception):
    """Raised when CLI input validation fails."""


def validate_inputs(change: str, repo: Path) -> None:
    """Validate CLI inputs before starting the pipeline.

    Checks:
    - repo path exists and is a git repo
    - openspec change directory exists in the repo
    - claude CLI is in PATH
    - gh CLI is in PATH
    """
    if not repo.exists():
        raise ValidationError(f"Repository path does not exist: {repo}")

    if not (repo / ".git").exists():
        raise ValidationError(f"Not a git repository: {repo}")

    changes_root = repo / "openspec" / "changes"
    change_dir = (changes_root / change).resolve()
    if not change_dir.is_relative_to(changes_root.resolve()):
        raise ValidationError(f"Invalid change name (path traversal): {change}")
    if not change_dir.exists():
        raise ValidationError(f"Change directory not found: {change_dir}")

    if shutil.which("claude") is None:
        raise ValidationError("claude CLI not found in PATH")

    if shutil.which("gh") is None:
        raise ValidationError("gh CLI not found in PATH")


@app.command()
def run(
    change: str = typer.Option(..., help="OpenSpec change name to implement"),
    repo: Path = typer.Option(..., help="Path to the target repository"),
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
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print plan without executing"
    ),
) -> None:
    """Run the action-harness pipeline for an OpenSpec change.

    Validates inputs, creates an isolated worktree, dispatches a Claude Code
    worker via opsx:apply, runs eval (pytest, ruff, mypy), retries with
    structured feedback on failure, and opens a PR for human review.

    The change must exist at REPO/openspec/changes/NAME/.
    """
    repo = repo.resolve()

    try:
        validate_inputs(change, repo)
    except ValidationError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    if dry_run:
        profile = profile_repo(repo)
        worktree_path = f"/tmp/action-harness/worktrees/harness/{change}"
        typer.echo(f"Dry-run plan for change '{change}':")
        typer.echo(f"  repo: {repo}")
        typer.echo(f"  worktree: {worktree_path}")
        typer.echo(f"  branch: harness/{change}")
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
        typer.echo(f"  pr title: [harness] {change}")
        typer.echo(f"  max retries: {max_retries}")
        raise typer.Exit(code=0)

    from action_harness.pipeline import run_pipeline

    pr_result, manifest = run_pipeline(
        change_name=change,
        repo=repo,
        max_retries=max_retries,
        max_turns=max_turns,
        model=model,
        effort=effort,
        max_budget_usd=max_budget_usd,
        permission_mode=permission_mode,
        verbose=verbose,
    )

    if manifest.manifest_path:
        typer.echo(f"[pipeline] manifest saved to {manifest.manifest_path}", err=True)

    if not pr_result.success:
        raise typer.Exit(code=1)
