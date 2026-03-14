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
    change: str = typer.Option(..., help="OpenSpec change name to implement"),
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
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print plan without executing"
    ),
) -> None:
    """Run the action-harness pipeline for an OpenSpec change.

    Validates inputs, creates an isolated worktree, dispatches a Claude Code
    worker via opsx:apply, runs eval (pytest, ruff, mypy), retries with
    structured feedback on failure, and opens a PR for human review.

    The `--repo` flag accepts a local path (e.g., `.` or `/abs/path`),
    GitHub shorthand (e.g., `owner/repo`), or a full URL
    (e.g., `https://github.com/owner/repo` or `git@github.com:owner/repo.git`).

    The change must exist at REPO/openspec/changes/NAME/.
    """
    resolved_home = _resolve_harness_home(harness_home)

    # Resolve repo: local path or remote reference
    from action_harness.repo import resolve_repo

    try:
        resolved_repo, repo_name = resolve_repo(repo, resolved_home, verbose=verbose)
    except ValidationError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    try:
        validate_inputs(change, resolved_repo)
    except ValidationError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    # Determine if this is a managed repo (cloned to harness home)
    is_managed = _is_managed_repo(resolved_repo, resolved_home)

    if dry_run:
        profile = profile_repo(resolved_repo)
        if is_managed:
            workspace_path = str(resolved_home / "workspaces" / repo_name / change)
        else:
            workspace_path = f"/tmp/action-harness-*/{change}"
        typer.echo(f"Dry-run plan for change '{change}':")
        typer.echo(f"  repo: {resolved_repo}")
        typer.echo(f"  worktree: {workspace_path}")
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
