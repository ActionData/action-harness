"""Pre-dispatch preflight checks for the pipeline.

Runs deterministic validation between worktree creation and worker
dispatch to catch environment problems early — before wasting tokens
on a Claude Code worker session.
"""

import shlex
import shutil
import subprocess
from pathlib import Path

import typer

from action_harness.models import PreflightResult
from action_harness.prerequisites import is_prerequisite_satisfied, read_prerequisites


def check_worktree_clean(worktree_path: Path) -> bool:
    """Check that the worktree has no uncommitted changes.

    Runs ``git status --porcelain`` in the worktree. Returns True if
    the output is empty (clean working directory). Logs dirty files on
    failure.
    """
    typer.echo(f"[preflight] checking worktree clean: {worktree_path}", err=True)
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        typer.echo(f"[preflight] worktree_clean: git status failed: {exc}", err=True)
        return False

    if result.returncode != 0:
        typer.echo(
            f"[preflight] worktree_clean: git status exited {result.returncode}: "
            f"{result.stderr.strip()}",
            err=True,
        )
        return False

    output = result.stdout.strip()
    if output:
        dirty_count = len(output.splitlines())
        typer.echo(
            f"[preflight] worktree_clean: FAILED — {dirty_count} dirty file(s)",
            err=True,
        )
        return False

    typer.echo("[preflight] worktree_clean: passed", err=True)
    return True


def check_git_remote(worktree_path: Path, verbose: bool = False) -> bool:
    """Check that the git remote 'origin' is reachable.

    Runs ``git ls-remote --exit-code origin HEAD`` with a 30-second
    timeout. Returns True on exit code 0.
    """
    typer.echo("[preflight] checking git remote reachable", err=True)
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", "origin", "HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        typer.echo(
            "[preflight] git_remote: FAILED — timed out after 30s",
            err=True,
        )
        return False
    except (FileNotFoundError, OSError) as exc:
        typer.echo(f"[preflight] git_remote: FAILED — {exc}", err=True)
        return False

    if result.returncode != 0:
        typer.echo(
            f"[preflight] git_remote: FAILED — exit {result.returncode}: "
            f"{result.stderr.strip()}",
            err=True,
        )
        return False

    if verbose:
        typer.echo("[preflight] git_remote: passed", err=True)
    else:
        typer.echo("[preflight] git_remote: passed", err=True)
    return True


def check_eval_tools(eval_commands: list[str]) -> tuple[bool, list[str]]:
    """Check that the binaries for eval commands are available in PATH.

    Extracts the first token (tool binary) from each eval command,
    deduplicates, and checks each with ``shutil.which()``.

    Returns ``(all_found, missing_tools)`` where ``missing_tools`` lists
    the names of tools not found in PATH.
    """
    typer.echo(
        f"[preflight] checking eval tool availability ({len(eval_commands)} command(s))",
        err=True,
    )
    seen: set[str] = set()
    missing: list[str] = []

    for cmd in eval_commands:
        try:
            tokens = shlex.split(cmd)
        except ValueError:
            # Malformed command — skip rather than crash preflight
            typer.echo(
                f"[preflight] eval_tools: warning — could not parse command: {cmd}",
                err=True,
            )
            continue
        if not tokens:
            continue
        tool = tokens[0]
        if tool in seen:
            continue
        seen.add(tool)

        if shutil.which(tool) is None:
            missing.append(tool)

    if missing:
        typer.echo(
            f"[preflight] eval_tools: FAILED — missing: {', '.join(missing)}",
            err=True,
        )
        return False, missing

    typer.echo(f"[preflight] eval_tools: passed ({len(seen)} tool(s) found)", err=True)
    return True, []


def check_prerequisites(change_name: str, repo_path: Path) -> bool:
    """Check that all OpenSpec prerequisites for the change are satisfied.

    Reads prerequisites from the change's ``.openspec.yaml`` and checks
    each via ``is_prerequisite_satisfied()``. Returns True if all are met
    or if no prerequisites exist.
    """
    typer.echo(f"[preflight] checking prerequisites for '{change_name}'", err=True)
    change_dir = repo_path / "openspec" / "changes" / change_name
    if not change_dir.is_dir():
        typer.echo(
            f"[preflight] prerequisites: skipped — change dir not found: {change_dir}",
            err=True,
        )
        return True

    prereqs = read_prerequisites(change_dir)
    if not prereqs:
        typer.echo("[preflight] prerequisites: passed (none required)", err=True)
        return True

    unmet: list[str] = []
    for prereq_name in prereqs:
        if not is_prerequisite_satisfied(prereq_name, repo_path):
            unmet.append(prereq_name)

    if unmet:
        typer.echo(
            f"[preflight] prerequisites: FAILED — unmet: {', '.join(unmet)}",
            err=True,
        )
        return False

    typer.echo(
        f"[preflight] prerequisites: passed ({len(prereqs)} prerequisite(s) met)",
        err=True,
    )
    return True


def run_preflight(
    worktree_path: Path,
    eval_commands: list[str],
    change_name: str | None,
    repo_path: Path,
    verbose: bool = False,
) -> PreflightResult:
    """Run all pre-dispatch preflight checks.

    Checks run in order:
    1. Worktree is clean (no uncommitted changes)
    2. Git remote is reachable
    3. Eval tool binaries exist
    4. OpenSpec prerequisites met (change mode only)

    Returns a ``PreflightResult`` with per-check pass/fail details.
    Overall success requires all checks to pass.
    """
    typer.echo("[preflight] starting pre-dispatch checks", err=True)

    checks: dict[str, bool] = {}
    failed: list[str] = []

    # 1. Worktree clean
    clean = check_worktree_clean(worktree_path)
    checks["worktree_clean"] = clean
    if not clean:
        failed.append("worktree_clean")

    # 2. Git remote reachable
    remote_ok = check_git_remote(worktree_path, verbose=verbose)
    checks["git_remote"] = remote_ok
    if not remote_ok:
        failed.append("git_remote")

    # 3. Eval tools available
    tools_ok, missing = check_eval_tools(eval_commands)
    checks["eval_tools"] = tools_ok
    if not tools_ok:
        failed.append("eval_tools")

    # 4. Prerequisites (change mode only)
    if change_name is not None:
        prereqs_ok = check_prerequisites(change_name, repo_path)
        checks["prerequisites"] = prereqs_ok
        if not prereqs_ok:
            failed.append("prerequisites")

    success = len(failed) == 0
    if success:
        typer.echo("[preflight] all checks passed", err=True)
    else:
        typer.echo(f"[preflight] FAILED checks: {', '.join(failed)}", err=True)

    return PreflightResult(
        success=success,
        stage="preflight",
        checks=checks,
        failed_checks=failed,
        error=f"Preflight failed: {', '.join(failed)}" if failed else None,
    )
