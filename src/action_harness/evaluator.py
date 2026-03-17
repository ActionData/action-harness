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

__all__ = ["BOOTSTRAP_EVAL_COMMANDS", "run_eval", "run_baseline_eval", "format_feedback"]

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


def run_baseline_eval(
    worktree_path: Path,
    eval_commands: list[str],
    verbose: bool = False,
) -> dict[str, bool]:
    """Run all eval commands in the worktree to establish a baseline.

    Runs EVERY command regardless of failures. Returns a dict mapping
    each command string to True (passed) or False (failed).
    """
    typer.echo(
        f"[baseline-eval] running {len(eval_commands)} eval command(s) at baseline",
        err=True,
    )

    venv_dir = os.environ.get("VIRTUAL_ENV")
    clean_env = {k: v for k, v in os.environ.items() if k not in _STRIPPED_ENV_VARS}
    if venv_dir and "PATH" in clean_env:
        venv_bin = venv_dir + "/bin"
        clean_env["PATH"] = os.pathsep.join(
            seg for seg in clean_env["PATH"].split(os.pathsep) if seg != venv_bin
        )

    results: dict[str, bool] = {}

    for i, cmd_str in enumerate(eval_commands):
        if verbose:
            typer.echo(f"  [{i + 1}/{len(eval_commands)}] {cmd_str}", err=True)

        try:
            result = subprocess.run(
                shlex.split(cmd_str),
                cwd=worktree_path,
                capture_output=True,
                text=True,
                env=clean_env,
                timeout=120,
            )
            passed = result.returncode == 0
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as e:
            typer.echo(
                f"[baseline-eval] ERROR: failed to run '{cmd_str}': {e}", err=True
            )
            passed = False

        results[cmd_str] = passed
        status = "passed" if passed else "FAILED"
        typer.echo(f"[baseline-eval] {cmd_str}: {status}", err=True)

    pass_count = sum(1 for v in results.values() if v)
    typer.echo(
        f"[baseline-eval] complete: {pass_count}/{len(eval_commands)} passed",
        err=True,
    )
    return results


def run_eval(
    worktree_path: Path,
    eval_commands: list[str] | None = None,
    verbose: bool = False,
    logger: EventLogger | None = None,
    baseline: dict[str, bool] | None = None,
) -> EvalResult:
    """Run eval commands in the worktree. Stop on first regression.

    Each command is run as a subprocess. Exit code 0 = pass, nonzero = fail.
    On failure, formats structured feedback for the worker agent.

    When ``baseline`` is provided, only regressions (commands that were passing
    at baseline but now fail) cause eval failure. Pre-existing failures (commands
    that were already failing at baseline) are logged and added to
    ``pre_existing_failures`` but do not block.
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
    pre_existing_failures: list[str] = []
    first_regression_command: str | None = None
    first_regression_feedback: str | None = None

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
                timeout=120,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as e:
            typer.echo(f"[eval] ERROR: failed to run '{cmd_str}': {e}", err=True)
            # Check if this was a pre-existing failure at baseline
            if baseline is not None and not baseline.get(cmd_str, True):
                typer.echo(
                    f"[eval] pre-existing failure (was already failing at baseline): {cmd_str}",
                    err=True,
                )
                pre_existing_failures.append(cmd_str)
                continue
            return EvalResult(
                success=False,
                stage="eval",
                error=f"Failed to execute: {cmd_str}: {e}",
                commands_run=i + 1,
                commands_passed=commands_passed,
                failed_command=cmd_str,
                pre_existing_failures=pre_existing_failures,
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

            # Check if this was a pre-existing failure at baseline
            if baseline is not None and not baseline.get(cmd_str, True):
                typer.echo(
                    f"[eval] pre-existing failure (was already failing at baseline): {cmd_str}",
                    err=True,
                )
                pre_existing_failures.append(cmd_str)
                continue

            # This is a regression (or no baseline provided)
            feedback = format_feedback(cmd_str, result.returncode, output)

            if baseline is not None:
                # With baseline: record first regression but continue to find
                # all pre-existing failures
                if first_regression_command is None:
                    first_regression_command = cmd_str
                    first_regression_feedback = feedback
                continue

            # Without baseline: stop on first failure (original behavior)
            return EvalResult(
                success=False,
                stage="eval",
                error=f"Eval failed: {cmd_str}",
                commands_run=i + 1,
                commands_passed=commands_passed,
                failed_command=cmd_str,
                feedback_prompt=feedback,
                pre_existing_failures=pre_existing_failures,
            )

        commands_passed += 1
        if logger is not None and hasattr(logger, "emit"):
            logger.emit("eval.command.passed", stage="eval", command=cmd_str)
        if verbose:
            typer.echo(f"  [{i + 1}/{len(commands)}] passed", err=True)

    # If we had a regression when using baseline mode, report it
    if first_regression_command is not None:
        typer.echo(
            f"[eval] regression detected: {first_regression_command}", err=True
        )
        return EvalResult(
            success=False,
            stage="eval",
            error=f"Eval failed: {first_regression_command}",
            commands_run=len(commands),
            commands_passed=commands_passed,
            failed_command=first_regression_command,
            feedback_prompt=first_regression_feedback,
            pre_existing_failures=pre_existing_failures,
        )

    typer.echo(f"[eval] all {commands_passed} command(s) passed", err=True)
    if pre_existing_failures:
        typer.echo(
            f"[eval] note: {len(pre_existing_failures)} pre-existing failure(s) ignored",
            err=True,
        )
    return EvalResult(
        success=True,
        stage="eval",
        commands_run=len(commands),
        commands_passed=commands_passed,
        pre_existing_failures=pre_existing_failures,
    )
