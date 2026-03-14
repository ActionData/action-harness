"""OpenSpec review agent: spec validation, semantic review, automated archival."""

import json
import subprocess
import time
from pathlib import Path

import typer

from action_harness.models import OpenSpecReviewResult
from action_harness.worker import count_commits_ahead

REVIEW_SYSTEM_PROMPT = """\
You are the OpenSpec review agent for the change '{change_name}'.

Your job is to validate that the OpenSpec lifecycle is complete and archive the change.

Steps:
1. Read openspec/changes/{change_name}/tasks.md and verify ALL tasks are marked [x].
   Count total tasks and completed tasks.
2. Run `openspec validate {change_name}` and check for errors.
3. Read the change's specs (under openspec/changes/{change_name}/specs/) and compare
   against the implementation diff to assess semantic alignment. This is advisory —
   note gaps but do not block archival for semantic issues alone.
4. If structural checks pass (all tasks [x] AND validation clean), run
   `openspec archive {change_name} -y` and commit the results.
5. Output a final JSON block with exactly these keys:

```json
{{
  "status": "approved" or "findings",
  "tasks_total": <int>,
  "tasks_complete": <int>,
  "validation_passed": <bool>,
  "semantic_review_passed": <bool>,
  "findings": [<list of strings describing any issues>],
  "archived": <bool>
}}
```

For OpenSpec conventions (delta spec rules, archive semantics, validation), consult
Fission-AI/OpenSpec on deepwiki.

Important: structural validation (tasks complete + openspec validate) is the hard gate.
Semantic review is advisory. If structural checks pass, archive even if you have
semantic findings — include those findings in your output for informational purposes.
"""


def build_review_prompt(change_name: str) -> str:
    """Build the system prompt for the OpenSpec review agent."""
    return REVIEW_SYSTEM_PROMPT.format(change_name=change_name)


def dispatch_openspec_review(
    change_name: str,
    worktree_path: Path,
    base_branch: str = "main",
    max_turns: int = 200,
    permission_mode: str = "bypassPermissions",
    verbose: bool = False,
) -> tuple[str, float]:
    """Dispatch the OpenSpec review agent via Claude Code CLI.

    Returns a tuple of (raw_stdout, duration_seconds).
    """
    typer.echo(f"[openspec-review] dispatching for '{change_name}'", err=True)

    system_prompt = build_review_prompt(change_name)
    user_prompt = (
        f"Review the OpenSpec change '{change_name}' — validate tasks, "
        f"run structural checks, perform semantic review, and archive if ready."
    )

    cmd = [
        "claude",
        "-p",
        user_prompt,
        "--system-prompt",
        system_prompt,
        "--output-format",
        "json",
        "--max-turns",
        str(max_turns),
        "--permission-mode",
        permission_mode,
    ]

    if verbose:
        typer.echo(f"  cwd: {worktree_path}", err=True)
        typer.echo(f"  cmd: {' '.join(cmd[:6])}...", err=True)

    start_time = time.monotonic()

    result = subprocess.run(
        cmd,
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    duration = time.monotonic() - start_time

    if result.returncode != 0:
        typer.echo(f"[openspec-review] failed (exit {result.returncode})", err=True)

    return result.stdout, duration


def parse_review_result(raw_output: str, duration: float) -> OpenSpecReviewResult:
    """Parse the review agent's JSON output into an OpenSpecReviewResult.

    Extracts the JSON block from the claude CLI output's ``result`` field.
    If parsing fails, returns an error result.
    """
    try:
        output_data = json.loads(raw_output)
        result_text = output_data.get("result", "")
    except json.JSONDecodeError:
        return OpenSpecReviewResult(
            success=False,
            error="Failed to parse review output: invalid JSON from CLI",
            duration_seconds=duration,
        )

    # Extract the JSON block from the result text
    review_data = _extract_json_block(result_text)
    if review_data is None:
        return OpenSpecReviewResult(
            success=False,
            error="Failed to parse review output: no JSON block found in result",
            duration_seconds=duration,
        )

    status = review_data.get("status", "findings")
    findings = review_data.get("findings", [])

    return OpenSpecReviewResult(
        success=status == "approved",
        duration_seconds=duration,
        tasks_total=review_data.get("tasks_total", 0),
        tasks_complete=review_data.get("tasks_complete", 0),
        validation_passed=review_data.get("validation_passed", False),
        semantic_review_passed=review_data.get("semantic_review_passed", False),
        findings=findings if isinstance(findings, list) else [str(findings)],
        archived=review_data.get("archived", False),
    )


def _extract_json_block(text: str) -> dict | None:  # type: ignore[type-arg]
    """Extract a JSON object from text that may contain surrounding prose.

    Tries to parse the entire text as JSON first. If that fails, looks for
    a JSON block delimited by ```json ... ``` or braces.
    """
    # Try the whole text first
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    if not isinstance(text, str):
        return None

    # Look for ```json ... ``` fenced block
    import re

    fenced = re.search(r"```json\s*\n(.*?)```", text, re.DOTALL)
    if fenced:
        try:
            data = json.loads(fenced.group(1))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Look for the last { ... } block (the agent may produce prose before it)
    brace_start = text.rfind("{")
    if brace_start == -1:
        return None

    # Find matching closing brace
    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(text[brace_start : i + 1])
                    if isinstance(data, dict):
                        return data
                except json.JSONDecodeError:
                    pass
                break

    return None


def push_archive_if_needed(
    worktree_path: Path,
    base_branch: str,
    commits_before: int,
    verbose: bool = False,
) -> tuple[bool, str | None]:
    """Push archive commits if the review agent created new ones.

    Returns (pushed: bool, error: str | None).
    """
    commits_after = count_commits_ahead(worktree_path, base_branch)
    new_commits = commits_after - commits_before

    if new_commits <= 0:
        if verbose:
            typer.echo("[openspec-review] no new commits to push", err=True)
        return False, None

    typer.echo(f"[openspec-review] {new_commits} new commit(s), pushing", err=True)

    try:
        push_result = subprocess.run(
            ["git", "push", "origin", "HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError) as e:
        return False, f"git push failed: {e}"

    if push_result.returncode != 0:
        return False, f"git push failed: {push_result.stderr.strip()}"

    if verbose:
        typer.echo("[openspec-review] push succeeded", err=True)

    return True, None
