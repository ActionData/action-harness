"""Protected paths detection for pipeline PRs.

Reads glob patterns from `.harness/protected-paths.yml` in the target repo,
checks the diff against those patterns, and flags PRs that touch protected files.
"""

import fnmatch
import subprocess
from pathlib import Path

import typer
import yaml


def load_protected_patterns(repo_path: Path) -> list[str]:
    """Read protected file patterns from `.harness/protected-paths.yml`.

    Returns the list of glob patterns. Returns ``[]`` if the file is missing,
    malformed, or lacks a ``protected`` key.
    """
    config_path = repo_path / ".harness" / "protected-paths.yml"

    if not config_path.exists():
        typer.echo("[protection] no .harness/protected-paths.yml found", err=True)
        return []

    try:
        raw = config_path.read_text()
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        typer.echo(f"[protection] warning: malformed YAML in {config_path}: {e}", err=True)
        return []

    if not isinstance(data, dict) or "protected" not in data:
        typer.echo(f"[protection] warning: missing 'protected' key in {config_path}", err=True)
        return []

    patterns = data["protected"]
    if not isinstance(patterns, list):
        typer.echo(f"[protection] warning: 'protected' is not a list in {config_path}", err=True)
        return []

    return [str(p) for p in patterns]


def check_protected_files(changed_files: list[str], patterns: list[str]) -> list[str]:
    """Match changed files against protected patterns using fnmatch.

    Returns the list of changed files that match any pattern.
    """
    protected: list[str] = []
    for f in changed_files:
        for pattern in patterns:
            if fnmatch.fnmatch(f, pattern):
                protected.append(f)
                break
    return protected


def get_changed_files(worktree_path: Path, base_branch: str) -> list[str]:
    """Get the list of changed files via ``git diff --name-only``.

    Compares ``origin/<base_branch>..HEAD`` in the worktree.
    Returns ``[]`` on failure.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"origin/{base_branch}..HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            typer.echo(f"[protection] warning: git diff failed: {result.stderr.strip()}", err=True)
            return []
        return [line for line in result.stdout.strip().splitlines() if line]
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[protection] warning: git diff failed: {e}", err=True)
        return []


def flag_pr_protected(
    pr_url: str,
    protected_files: list[str],
    worktree_path: Path,
    verbose: bool,
) -> None:
    """Post a PR comment listing protected files and add the ``protected-paths`` label.

    Non-fatal — errors are logged to stderr and swallowed.
    Does nothing if ``protected_files`` is empty.
    """
    if not protected_files:
        return

    # Build comment body
    lines = [
        "## ⚠️ Protected Files Modified",
        "",
        "The following protected files were modified and require human review:",
        "",
    ]
    for f in protected_files:
        lines.append(f"- `{f}`")
    lines.append("")
    lines.append("This PR has been labeled `protected-paths` for human review.")
    body = "\n".join(lines)

    # Post comment
    try:
        result = subprocess.run(
            ["gh", "pr", "comment", pr_url, "--body", body],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            typer.echo(
                f"[protection] warning: gh pr comment failed: {result.stderr.strip()}",
                err=True,
            )
        elif verbose:
            typer.echo("[protection] posted protected-paths comment on PR", err=True)
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[protection] warning: gh pr comment failed: {e}", err=True)

    # Add label
    try:
        result = subprocess.run(
            ["gh", "pr", "edit", pr_url, "--add-label", "protected-paths"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            typer.echo(
                f"[protection] warning: gh pr edit --add-label failed: {result.stderr.strip()}",
                err=True,
            )
        elif verbose:
            typer.echo("[protection] added protected-paths label to PR", err=True)
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[protection] warning: gh pr edit --add-label failed: {e}", err=True)
