"""CLI entrypoint for action-harness."""

import shutil
from pathlib import Path

import typer

app = typer.Typer(
    name="action-harness",
    add_completion=False,
    rich_markup_mode="markdown",
)

BOOTSTRAP_EVAL_COMMANDS = [
    "uv run pytest -v",
    "uv run ruff check .",
    "uv run ruff format --check .",
    "uv run mypy src/",
]


@app.callback()
def main() -> None:
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
    verbose: bool = typer.Option(False, help="Show detailed subprocess output on stderr"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print plan without executing"
    ),
) -> None:
    """Run the action-harness pipeline for an OpenSpec change.

    Currently validates inputs and exits. The full pipeline (worktree isolation,
    Claude Code worker dispatch, eval, retry, PR creation) is under construction.

    The change must exist at REPO/openspec/changes/NAME/.
    """
    repo = repo.resolve()

    try:
        validate_inputs(change, repo)
    except ValidationError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    if dry_run:
        worktree_path = f"/tmp/action-harness/worktrees/harness/{change}"
        typer.echo(f"Dry-run plan for change '{change}':")
        typer.echo(f"  repo: {repo}")
        typer.echo(f"  worktree: {worktree_path}")
        typer.echo(f"  branch: harness/{change}")
        typer.echo(f"  worker: claude --output-format json --max-turns {max_turns}")
        typer.echo("  eval commands:")
        for cmd in BOOTSTRAP_EVAL_COMMANDS:
            typer.echo(f"    - {cmd}")
        typer.echo(f"  pr title: [harness] {change}")
        typer.echo(f"  max retries: {max_retries}")
        raise typer.Exit(code=0)

    typer.echo(f"Starting pipeline for change '{change}' in {repo}", err=True)
    typer.echo(f"  max_retries={max_retries}, max_turns={max_turns}", err=True)
