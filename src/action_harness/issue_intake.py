"""GitHub issue intake: read issues, detect OpenSpec references, build prompts."""

import json
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

import typer

from action_harness.models import ValidationError


class IssueData(NamedTuple):
    """Data extracted from a GitHub issue."""

    title: str
    body: str
    state: str


def read_issue(issue_number: int, repo_path: Path) -> IssueData:
    """Read a GitHub issue via gh CLI and return its data.

    Raises ValidationError if the issue is not found or is already closed.
    """
    typer.echo(f"[issue-intake] reading issue #{issue_number} from {repo_path}", err=True)

    result = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "title,body,state"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        typer.echo(
            f"[issue-intake] gh issue view failed (exit {result.returncode}): "
            f"{result.stderr.strip()}",
            err=True,
        )
        raise ValidationError(f"Issue #{issue_number} not found")

    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as e:
        typer.echo(
            f"[issue-intake] failed to parse gh output: {e}",
            err=True,
        )
        raise ValidationError(f"Issue #{issue_number}: malformed response from gh") from e

    try:
        title = data["title"]
        state = data["state"]
    except KeyError as e:
        raise ValidationError(f"Issue #{issue_number}: missing field {e} in gh response") from e

    issue = IssueData(
        title=title,
        body=data.get("body") or "",
        state=state,
    )

    if issue.state == "CLOSED":
        typer.echo(f"[issue-intake] issue #{issue_number} is already closed", err=True)
        raise ValidationError(f"Issue #{issue_number} is already closed")

    typer.echo(
        f"[issue-intake] read issue #{issue_number}: {issue.title!r} (state={issue.state})",
        err=True,
    )
    return issue


_CHANGE_PATTERNS = [
    re.compile(r"openspec:([a-z0-9-]+)"),
    re.compile(r"change:\s*([a-z0-9-]+)"),
    re.compile(r"openspec/changes/([a-z0-9-]+)"),
]


def detect_openspec_change(body: str, repo_path: Path) -> str | None:
    """Scan issue body for OpenSpec change references.

    Checks for patterns like ``openspec:change-name``, ``change: change-name``,
    or ``openspec/changes/change-name``. For each pattern, checks all matches
    (not just the first) against the filesystem. Returns the first change name
    where the directory exists, None otherwise.
    """
    typer.echo("[issue-intake] scanning issue body for OpenSpec change references", err=True)

    for pattern in _CHANGE_PATTERNS:
        for match in pattern.finditer(body):
            name = match.group(1)
            change_dir = repo_path / "openspec" / "changes" / name
            if change_dir.is_dir():
                typer.echo(f"[issue-intake] detected change: {name}", err=True)
                return name
            typer.echo(
                f"[issue-intake] pattern matched '{name}' but directory does not exist",
                err=True,
            )

    typer.echo("[issue-intake] no OpenSpec change reference found", err=True)
    return None


def label_issue(issue_number: int, label: str, repo_path: Path, verbose: bool = False) -> None:
    """Add a label to a GitHub issue. Best-effort — never raises."""
    typer.echo(f"[issue-intake] labeling issue #{issue_number} with '{label}'", err=True)

    try:
        result = subprocess.run(
            ["gh", "issue", "edit", str(issue_number), "--add-label", label],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError) as e:
        typer.echo(
            f"[issue-intake] warning: failed to label issue #{issue_number}: {e}",
            err=True,
        )
        return

    if result.returncode != 0:
        typer.echo(
            f"[issue-intake] warning: failed to label issue #{issue_number}: "
            f"{result.stderr.strip()}",
            err=True,
        )
    elif verbose:
        typer.echo(f"[issue-intake] labeled issue #{issue_number} with '{label}'", err=True)


def comment_on_issue(issue_number: int, body: str, repo_path: Path, verbose: bool = False) -> None:
    """Post a comment on a GitHub issue. Best-effort — never raises."""
    typer.echo(f"[issue-intake] commenting on issue #{issue_number}", err=True)

    try:
        result = subprocess.run(
            ["gh", "issue", "comment", str(issue_number), "--body", body],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError) as e:
        typer.echo(
            f"[issue-intake] warning: failed to comment on issue #{issue_number}: {e}",
            err=True,
        )
        return

    if result.returncode != 0:
        typer.echo(
            f"[issue-intake] warning: failed to comment on issue #{issue_number}: "
            f"{result.stderr.strip()}",
            err=True,
        )
    elif verbose:
        typer.echo(f"[issue-intake] commented on issue #{issue_number}", err=True)


def build_issue_prompt(issue_number: int, title: str, body: str) -> str:
    """Build a freeform prompt from issue metadata."""
    return f"# GitHub Issue #{issue_number}: {title}\n\n{body}"
