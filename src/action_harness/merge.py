"""Auto-merge logic: gate checks, CI wait, PR merge, and blocked comments."""

import subprocess
from pathlib import Path

import typer

from action_harness.models import MergeResult

# Timeout for gh commands that should complete quickly (merge, comment).
_GH_COMMAND_TIMEOUT_SECONDS = 120


def merge_pr(
    pr_url: str,
    worktree_path: Path,
    delete_branch: bool = True,
    verbose: bool = False,
) -> MergeResult:
    """Merge a PR via `gh pr merge`. Returns MergeResult with outcome.

    Uses merge commits (--merge) and optionally deletes the branch.
    Logs outcome to stderr.
    """
    cmd = ["gh", "pr", "merge", pr_url, "--merge"]
    if delete_branch:
        cmd.append("--delete-branch")

    if verbose:
        typer.echo(f"[merge] running: {' '.join(cmd)}", err=True)

    try:
        result = subprocess.run(
            cmd,
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=_GH_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        typer.echo(
            f"[merge] gh pr merge timed out after {_GH_COMMAND_TIMEOUT_SECONDS}s",
            err=True,
        )
        return MergeResult(success=False, merged=False, error="gh pr merge timed out")
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[merge] gh pr merge failed: {e}", err=True)
        return MergeResult(success=False, merged=False, error=str(e))

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        typer.echo(f"[merge] gh pr merge failed: {error_msg}", err=True)
        return MergeResult(success=False, merged=False, error=error_msg)

    typer.echo("[merge] PR merged successfully", err=True)
    return MergeResult(success=True, merged=True)


def check_merge_gates(
    protected_files: list[str],
    findings_remain: bool,
    openspec_review_passed: bool,
    skip_review: bool,
) -> tuple[dict[str, bool], bool]:
    """Evaluate all merge gates (no short-circuit).

    Returns (gates_dict, all_passed) where gates_dict maps gate names
    to pass/fail for complete checklist reporting.
    """
    gates: dict[str, bool] = {
        "no_protected_files": len(protected_files) == 0,
        "review_clean": not findings_remain or skip_review,
        "openspec_review_passed": openspec_review_passed,
    }
    all_passed = all(gates.values())
    return gates, all_passed


def wait_for_ci(
    pr_url: str,
    worktree_path: Path,
    timeout_seconds: int = 600,
    verbose: bool = False,
) -> bool:
    """Wait for CI status checks to pass via `gh pr checks --watch`.

    Returns True if all checks pass, False on failure or timeout.
    """
    cmd = ["gh", "pr", "checks", pr_url, "--watch", "--fail-fast"]

    if verbose:
        typer.echo(f"[merge] waiting for CI: {' '.join(cmd)}", err=True)

    try:
        result = subprocess.run(
            cmd,
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        typer.echo(
            f"[merge] CI wait timed out after {timeout_seconds}s",
            err=True,
        )
        return False
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[merge] CI wait failed: {e}", err=True)
        return False

    if result.returncode != 0:
        typer.echo(f"[merge] CI checks failed: {result.stderr.strip()}", err=True)
        return False

    typer.echo("[merge] CI checks passed", err=True)
    return True


def post_merge_blocked_comment(
    pr_url: str,
    worktree_path: Path,
    gates: dict[str, bool],
    verbose: bool = False,
) -> None:
    """Post a PR comment explaining why auto-merge was blocked.

    Best-effort — logs warning on failure, never raises.
    """
    gate_labels = {
        "no_protected_files": "No protected files touched",
        "review_clean": "Review agents clean",
        "openspec_review_passed": "OpenSpec review passed",
    }

    lines = ["## Auto-merge blocked", ""]
    for gate_name, passed in gates.items():
        check = "[x]" if passed else "[ ]"
        label = gate_labels.get(gate_name, gate_name)
        lines.append(f"- {check} {label}")
    lines.append("")
    lines.append("This PR requires human review.")
    body = "\n".join(lines)

    try:
        result = subprocess.run(
            ["gh", "pr", "comment", pr_url, "--body", body],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=_GH_COMMAND_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            typer.echo(
                f"[merge] warning: failed to post blocked comment: {result.stderr.strip()}",
                err=True,
            )
        elif verbose:
            typer.echo("[merge] posted merge-blocked comment on PR", err=True)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as e:
        typer.echo(f"[merge] warning: failed to post blocked comment: {e}", err=True)
