"""OpenSpec review agent: spec validation, semantic review, and automated archival."""

import json
import subprocess
import time
from pathlib import Path

import typer

from action_harness.models import OpenSpecReviewResult
from action_harness.worker import count_commits_ahead

REVIEW_SYSTEM_PROMPT = """\
You are an OpenSpec review agent for the change '{change_name}'.

Your job is to validate the OpenSpec lifecycle is complete, perform semantic review, \
and archive the change if structural checks pass.

## Steps

1. **Check task completion**
   Read `openspec/changes/{change_name}/tasks.md` and verify every task is marked `[x]`.
   Count the total tasks and completed tasks.

2. **Run structural validation**
   Run: `openspec validate {change_name}`
   Check the output for errors. If there are errors, report them as findings.

3. **Semantic review (advisory)**
   Read the change's specs under `openspec/changes/{change_name}/specs/`.
   Compare the spec requirements against the actual code changes (use `git diff`).
   Note any gaps where the implementation doesn't match spec intent.
   This is advisory — findings here do NOT block archival.

4. **Archive if structural checks pass**
   If tasks are all complete AND validation is clean, run:
   `openspec archive {change_name} -y`
   Then commit the archive results:
   `git add -A && git commit -m "archive: {change_name}"`

5. **Output final result**
   Output a JSON block as your final message with exactly these keys:
   ```json
   {{
     "status": "approved" or "findings",
     "tasks_total": <int>,
     "tasks_complete": <int>,
     "validation_passed": <bool>,
     "semantic_review_passed": <bool>,
     "findings": [<list of strings>],
     "archived": <bool>
   }}
   ```

## References

For OpenSpec conventions (delta specs, archive semantics, validation rules), \
consult `Fission-AI/OpenSpec` on deepwiki.

## Rules

- Structural validation (tasks complete + `openspec validate` clean) is the hard gate.
- Semantic review is advisory — include findings but do NOT block archival.
- If structural checks fail, do NOT archive. Report findings.
- Always output the JSON block as your final message.
"""


def build_review_prompt(change_name: str) -> str:
    """Build the system prompt for the OpenSpec review agent."""
    return REVIEW_SYSTEM_PROMPT.format(change_name=change_name)


def dispatch_openspec_review(
    change_name: str,
    worktree_path: Path,
    base_branch: str = "main",
    max_turns: int = 50,
    permission_mode: str = "bypassPermissions",
    verbose: bool = False,
) -> OpenSpecReviewResult:
    """Dispatch an OpenSpec review agent and return the parsed result.

    Invokes the claude CLI as a subprocess in the worktree directory.
    After dispatch, pushes any archive commits to the remote.
    """
    typer.echo(f"[openspec-review] dispatching for '{change_name}'", err=True)

    system_prompt = build_review_prompt(change_name)
    user_prompt = (
        f"Review the OpenSpec change '{change_name}': validate tasks, "
        f"run structural validation, perform semantic review, and archive if appropriate."
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

    # Parse output
    raw_output = None
    if result.stdout:
        try:
            output_data = json.loads(result.stdout)
            raw_output = output_data.get("result")
        except json.JSONDecodeError:
            raw_output = result.stdout[:500]

    if result.returncode != 0:
        typer.echo(f"[openspec-review] failed (exit {result.returncode})", err=True)
        return OpenSpecReviewResult(
            success=False,
            error=f"Claude CLI exited with code {result.returncode}: {result.stderr[:500]}",
            duration_seconds=duration,
        )

    # Parse the review result
    review_result = parse_review_result(raw_output, duration)

    # Push archive commits if any
    if review_result.success and review_result.archived:
        commits = count_commits_ahead(worktree_path, base_branch)
        if commits > 0:
            push_result = _push_archive_commits(worktree_path, verbose)
            if not push_result.success:
                return push_result

    status = "approved" if review_result.success else "findings"
    typer.echo(f"[openspec-review] completed: status={status}", err=True)
    return review_result


def parse_review_result(raw_output: str | None, duration: float) -> OpenSpecReviewResult:
    """Parse the review agent's output into an OpenSpecReviewResult.

    Extracts the JSON block from the worker's output. Classifies as approved
    (status == "approved") or findings.
    """
    if not raw_output:
        return OpenSpecReviewResult(
            success=False,
            error="Failed to parse review output",
            duration_seconds=duration,
        )

    # Try to find a JSON block in the output
    json_data = _extract_json_block(raw_output)
    if json_data is None:
        return OpenSpecReviewResult(
            success=False,
            error="Failed to parse review output",
            duration_seconds=duration,
        )

    try:
        status = json_data.get("status", "findings")
        return OpenSpecReviewResult(
            success=status == "approved",
            duration_seconds=duration,
            tasks_total=json_data.get("tasks_total", 0),
            tasks_complete=json_data.get("tasks_complete", 0),
            validation_passed=json_data.get("validation_passed", False),
            semantic_review_passed=json_data.get("semantic_review_passed", False),
            findings=json_data.get("findings", []),
            archived=json_data.get("archived", False),
        )
    except (TypeError, ValueError):
        return OpenSpecReviewResult(
            success=False,
            error="Failed to parse review output",
            duration_seconds=duration,
        )


def _extract_json_block(text: str) -> dict | None:  # type: ignore[type-arg]
    """Extract a JSON object from text, trying the full text first then code blocks."""
    # Try parsing the entire text as JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Try to find a JSON block in markdown code fences
    import re

    pattern = re.compile(r"```(?:json)?\s*\n({.*?})\s*\n```", re.DOTALL)
    match = pattern.search(text)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Try to find a bare JSON object (last occurrence, as the final output)
    # Look for the last { ... } that parses as valid JSON
    last_brace = text.rfind("{")
    while last_brace >= 0:
        try:
            # Find the matching closing brace
            candidate = text[last_brace:]
            data = json.loads(candidate[: candidate.index("}") + 1])
            if isinstance(data, dict) and "status" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        # Try parsing from this brace to end
        try:
            data = json.loads(text[last_brace:])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        last_brace = text.rfind("{", 0, last_brace)

    return None


def _push_archive_commits(worktree_path: Path, verbose: bool = False) -> OpenSpecReviewResult:
    """Push archive commits to origin. Returns a failure result if push fails."""
    typer.echo("[openspec-review] pushing archive commits", err=True)

    try:
        push_result = subprocess.run(
            ["git", "push", "origin", "HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError) as e:
        typer.echo(f"[openspec-review] ERROR: git push failed: {e}", err=True)
        return OpenSpecReviewResult(
            success=False,
            error=f"git push failed: {e}",
        )

    if push_result.returncode != 0:
        typer.echo(f"[openspec-review] push failed: {push_result.stderr.strip()}", err=True)
        return OpenSpecReviewResult(
            success=False,
            error=push_result.stderr.strip(),
        )

    if verbose:
        typer.echo("  archive commits pushed", err=True)

    # Return a success marker — the caller will use the actual review result
    return OpenSpecReviewResult(success=True)
