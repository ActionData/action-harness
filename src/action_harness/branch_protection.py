"""GitHub API branch protection checks."""

import subprocess
from pathlib import Path

import typer

from action_harness.worktree import _get_default_branch


def _get_remote_owner_repo(repo_path: Path) -> str | None:
    """Extract owner/repo from git remote URL."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None

        url = result.stdout.strip()
        # Handle SSH: git@github.com:owner/repo.git
        if url.startswith("git@") and "github.com" in url:
            parts = url.split(":")[-1]
            return parts.removesuffix(".git")
        # Handle HTTPS: https://github.com/owner/repo.git
        if "github.com" in url:
            parts = url.rstrip("/").removesuffix(".git").split("github.com/")[-1]
            return parts
        return None
    except FileNotFoundError:
        return None


def check_branch_protection(repo_path: Path) -> bool | None:
    """Check if the default branch has branch protection rules.

    Uses gh API to query GitHub. Returns:
    - True if branch protection is configured
    - False if no branch protection
    - None if gh is unavailable, unauthenticated, or the check fails
    """
    typer.echo("[branch_protection] checking branch protection via gh API", err=True)

    # Check if gh is available
    try:
        gh_check = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
        )
        if gh_check.returncode != 0:
            typer.echo(
                "[branch_protection] gh not authenticated, skipping",
                err=True,
            )
            return None
    except FileNotFoundError:
        typer.echo("[branch_protection] gh CLI not found, skipping", err=True)
        return None

    owner_repo = _get_remote_owner_repo(repo_path)
    if owner_repo is None:
        typer.echo(
            "[branch_protection] could not determine owner/repo, skipping",
            err=True,
        )
        return None

    branch = _get_default_branch(repo_path)

    typer.echo(
        f"[branch_protection] checking {owner_repo} branch {branch}",
        err=True,
    )

    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{owner_repo}/branches/{branch}/protection",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            typer.echo("[branch_protection] protection enabled", err=True)
            return True
        # 404 means no protection
        if "404" in result.stderr or "Not Found" in result.stderr:
            typer.echo("[branch_protection] no protection configured", err=True)
            return False
        typer.echo(
            f"[branch_protection] API error: {result.stderr.strip()[:200]}",
            err=True,
        )
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        typer.echo("[branch_protection] gh command failed, skipping", err=True)
        return None
