"""Subprocess eval runner."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from action_harness.models import EvalResult
from action_harness.profiler import BOOTSTRAP_EVAL_COMMANDS

if TYPE_CHECKING:
    from action_harness.event_log import EventLogger

__all__ = ["BOOTSTRAP_EVAL_COMMANDS", "run_eval", "format_feedback"]

_STRIPPED_ENV_VARS = ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT")


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
    logger: EventLogger | None = None,
) -> EvalResult:
    """Run eval commands in the worktree. Stop on first failure.

    Each command is run as a subprocess. Exit code 0 = pass, nonzero = fail.
    On failure, formats structured feedback for the worker agent.
    """
    commands = eval_commands or BOOTSTRAP_EVAL_COMMANDS
    typer.echo(f"[eval] running {len(commands)} eval command(s)", err=True)

    venv_dir = os.environ.get("VIRTUAL_ENV")
    clean_env = {k: v for k, v in os.environ.items() if k not in _STRIPPED_ENV_VARS}
    if venv_dir and "PATH" in clean_env:
        venv_bin = venv_dir + "/bin"
        clean_env["PATH"] = os.pathsep.join(
            seg for seg in clean_env["PATH"].split(os.pathsep) if seg != venv_bin
        )

    commands_passed = 0

    for i, cmd_str in enumerate(commands):
        if verbose:
            typer.echo(f"  [{i + 1}/{len(commands)}] {cmd_str}", err=True)

        try:
            result = subprocess.run(
                shlex.split(cmd_str),
                cwd=worktree_path,
                capture_output=True,
                text=True,
                env=clean_env,
            )
        except (FileNotFoundError, OSError) as e:
            typer.echo(f"[eval] ERROR: failed to run '{cmd_str}': {e}", err=True)
            return EvalResult(
                success=False,
                stage="eval",
                error=f"Failed to execute: {cmd_str}: {e}",
                commands_run=i + 1,
                commands_passed=commands_passed,
                failed_command=cmd_str,
            )

        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            typer.echo(f"[eval] FAILED: {cmd_str} (exit {result.returncode})", err=True)
            if logger is not None:
                logger.emit(
                    "eval.command.failed",
                    stage="eval",
                    command=cmd_str,
                    exit_code=result.returncode,
                )
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
        if logger is not None and hasattr(logger, "emit"):
            logger.emit("eval.command.passed", stage="eval", command=cmd_str)
        if verbose:
            typer.echo(f"  [{i + 1}/{len(commands)}] passed", err=True)

    typer.echo(f"[eval] all {commands_passed} command(s) passed", err=True)
    return EvalResult(
        success=True,
        stage="eval",
        commands_run=len(commands),
        commands_passed=commands_passed,
    )
