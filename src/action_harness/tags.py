"""Git tag management for rollback points and shipped feature markers."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import typer


def create_tag(repo_path: Path, tag_name: str, commit: str = "HEAD") -> str:
    """Create a git tag and return the actual tag name used.

    If tag already exists, append a timestamp suffix and retry once.
    Raises RuntimeError if the timestamped tag also collides.
    """
    typer.echo(f"[tags] creating tag '{tag_name}' on {commit}", err=True)

    result = subprocess.run(
        ["git", "tag", tag_name, commit],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode == 0:
        typer.echo(f"[tags] created tag '{tag_name}'", err=True)
        return tag_name

    # Tag exists — retry with timestamp suffix
    now = datetime.now(UTC)
    ts = now.strftime("%Y%m%d-%H%M%S-%f")
    suffixed = f"{tag_name}-{ts}"
    typer.echo(
        f"[tags] tag '{tag_name}' exists, retrying as '{suffixed}'",
        err=True,
    )

    retry = subprocess.run(
        ["git", "tag", suffixed, commit],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if retry.returncode == 0:
        typer.echo(f"[tags] created tag '{suffixed}'", err=True)
        return suffixed

    raise RuntimeError(f"Failed to create tag '{suffixed}': {retry.stderr.strip()}")


def push_tag(repo_path: Path, tag_name: str) -> bool:
    """Push a single tag to origin. Returns True on success.

    On failure, logs a warning to stderr and returns False (non-fatal).
    """
    typer.echo(f"[tags] pushing tag '{tag_name}'", err=True)
    try:
        result = subprocess.run(
            ["git", "push", "origin", tag_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        typer.echo(f"[tags] warning: push failed for '{tag_name}': {e}", err=True)
        return False

    if result.returncode != 0:
        typer.echo(
            f"[tags] warning: push failed for '{tag_name}': {result.stderr.strip()}",
            err=True,
        )
        return False

    typer.echo(f"[tags] pushed tag '{tag_name}'", err=True)
    return True


def list_tags(repo_path: Path, pattern: str) -> list[dict[str, str]]:
    """Return tags matching a glob pattern, sorted by date descending.

    Each dict has: tag, commit, date (ISO 8601), label (part after last /).
    """
    typer.echo(f"[tags] listing tags matching '{pattern}'", err=True)
    try:
        result = subprocess.run(
            [
                "git",
                "tag",
                "-l",
                pattern,
                "--sort=-creatordate",
                "--format=%(refname:strip=0)\t%(objectname:short)\t%(creatordate:iso-strict)",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        typer.echo(f"[tags] warning: list_tags failed: {e}", err=True)
        return []

    if result.returncode != 0:
        typer.echo(f"[tags] warning: list_tags failed: {result.stderr.strip()}", err=True)
        return []

    tags: list[dict[str, str]] = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        raw_tag = parts[0]
        # Strip refs/tags/ prefix if present
        tag = raw_tag.removeprefix("refs/tags/")
        commit = parts[1]
        date = parts[2]
        label = tag.rsplit("/", maxsplit=1)[-1]
        tags.append({"tag": tag, "commit": commit, "date": date, "label": label})

    typer.echo(f"[tags] found {len(tags)} matching tags", err=True)
    return tags


def get_latest_tag(repo_path: Path, pattern: str) -> str | None:
    """Return the most recent tag matching the pattern, or None."""
    tags = list_tags(repo_path, pattern)
    if not tags:
        return None
    return tags[0]["tag"]


def tag_pre_merge(repo_path: Path, label: str, base_branch: str) -> None:
    """Create harness/pre-merge/{label} on the base branch HEAD and push it."""
    typer.echo(
        f"[tags] tagging pre-merge for '{label}' on branch '{base_branch}'",
        err=True,
    )
    tag_name = f"harness/pre-merge/{label}"
    actual = create_tag(repo_path, tag_name, commit=base_branch)
    push_tag(repo_path, actual)
    typer.echo(f"[tags] pre-merge tag complete: {actual}", err=True)


def tag_shipped(repo_path: Path, label: str, pr_url: str) -> bool:
    """Create harness/shipped/{label} on the merge commit.

    Checks if the PR is merged via gh. Returns False if not merged or on error.
    """
    typer.echo(f"[tags] checking merge status for PR '{pr_url}'", err=True)
    try:
        result = subprocess.run(
            ["gh", "pr", "view", pr_url, "--json", "mergedAt,mergeCommitSha"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        typer.echo(f"[tags] error: gh pr view failed: {e}", err=True)
        return False

    if result.returncode != 0:
        typer.echo(
            f"[tags] error: gh pr view failed (exit {result.returncode}): {result.stderr.strip()}",
            err=True,
        )
        return False

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        typer.echo(f"[tags] error: invalid JSON from gh: {e}", err=True)
        return False

    merged_at = data.get("mergedAt")
    merge_commit = data.get("mergeCommitSha")

    if not merged_at or not merge_commit:
        typer.echo("[tags] PR is not merged yet", err=True)
        return False

    tag_name = f"harness/shipped/{label}"
    actual = create_tag(repo_path, tag_name, commit=merge_commit)
    push_tag(repo_path, actual)
    typer.echo(f"[tags] shipped tag complete: {actual}", err=True)
    return True
