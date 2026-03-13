"""CLI entrypoint for action-harness."""

import shutil
from pathlib import Path

import typer

app = typer.Typer(name="action-harness", add_completion=False)


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
) -> None:
    """Run the action-harness pipeline for an OpenSpec change."""
    repo = repo.resolve()

    try:
        validate_inputs(change, repo)
    except ValidationError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"Starting pipeline for change '{change}' in {repo}")
    typer.echo(f"  max_retries={max_retries}, max_turns={max_turns}")
