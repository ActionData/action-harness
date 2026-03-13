"""Subprocess eval runner."""

import subprocess
from pathlib import Path

import typer

from action_harness.models import EvalResult

BOOTSTRAP_EVAL_COMMANDS = [
    "uv run pytest -v",
    "uv run ruff check .",
    "uv run ruff format --check .",
    "uv run mypy src/",
]


def format_feedback(command: str, exit_code: int, output: str) -> str:
    """Format structured feedback for a failed eval command."""
    return (
        f"## Eval Failure\n\n"
        f"### Command: {command}\n"
        f"### Exit Code: {exit_code}\n"
        f"### Output:\n"
        f"```\n{output}\n```\n\n"
        f"Fix these issues and re-run the failing commands to verify."
    )


def run_eval(
    worktree_path: Path,
    eval_commands: list[str] | None = None,
    verbose: bool = False,
) -> EvalResult:
    """Run eval commands in the worktree. Stop on first failure.

    Each command is run as a subprocess. Exit code 0 = pass, nonzero = fail.
    On failure, formats structured feedback for the worker agent.
    """
    commands = eval_commands or BOOTSTRAP_EVAL_COMMANDS
    typer.echo(f"[eval] running {len(commands)} eval command(s)", err=True)

    commands_passed = 0

    for i, cmd_str in enumerate(commands):
        if verbose:
            typer.echo(f"  [{i + 1}/{len(commands)}] {cmd_str}", err=True)

        result = subprocess.run(
            cmd_str.split(),
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            typer.echo(f"[eval] FAILED: {cmd_str} (exit {result.returncode})", err=True)
            if verbose:
                preview = output[:500]
                typer.echo(f"  output preview: {preview}", err=True)

            feedback = format_feedback(cmd_str, result.returncode, output)

            return EvalResult(
                success=False,
                stage="eval",
                error=f"Eval failed: {cmd_str}",
                commands_run=i + 1,
                commands_passed=commands_passed,
                failed_command=cmd_str,
                feedback_prompt=feedback,
            )

        commands_passed += 1
        if verbose:
            typer.echo(f"  [{i + 1}/{len(commands)}] passed", err=True)

    typer.echo(f"[eval] all {commands_passed} command(s) passed", err=True)
    return EvalResult(
        success=True,
        stage="eval",
        commands_run=len(commands),
        commands_passed=commands_passed,
    )
