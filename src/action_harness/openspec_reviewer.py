"""OpenSpec review agent: spec validation, semantic review, automated archival."""

import json
import subprocess
import time
from pathlib import Path

import typer

from action_harness.agents import load_agent_prompt
from action_harness.models import OpenSpecReviewResult
from action_harness.parsing import extract_json_block
from action_harness.worker import count_commits_ahead

# JSON output block appended AFTER the persona text from openspec-reviewer.md.
# Step number "5." continues from steps 1-4 defined in the agent file.
# If the agent file's steps are renumbered, update the step number here.
_OPENSPEC_JSON_SUFFIX = """

5. Output a final JSON block with exactly these keys:

```json
{
  "status": "approved" or "findings" or "needs-human",
  "tasks_total": <int>,
  "tasks_complete": <int>,
  "human_tasks_remaining": <int>,
  "validation_passed": <bool>,
  "semantic_review_passed": <bool>,
  "findings": [<list of strings describing any issues>],
  "archived": <bool>
}
```
"""


def build_review_prompt(change_name: str, repo_path: Path, harness_agents_dir: Path) -> str:
    """Build the system prompt for the OpenSpec review agent.

    Loads the persona from file, formats {change_name} placeholders,
    then appends the JSON output block.
    """
    persona = load_agent_prompt("openspec-reviewer", repo_path, harness_agents_dir)
    # Use str.replace instead of str.format to avoid crashes on literal
    # braces in user-editable agent markdown files.
    prompt = persona.replace("{change_name}", change_name)
    return prompt + _OPENSPEC_JSON_SUFFIX


def dispatch_openspec_review(
    change_name: str,
    worktree_path: Path,
    repo_path: Path,
    harness_agents_dir: Path,
    base_branch: str = "main",
    max_turns: int = 200,
    model: str | None = None,
    effort: str | None = None,
    max_budget_usd: float | None = None,
    permission_mode: str = "bypassPermissions",
    verbose: bool = False,
) -> tuple[str, float]:
    """Dispatch the OpenSpec review agent via Claude Code CLI.

    Returns a tuple of (raw_stdout, duration_seconds).
    """
    typer.echo(f"[openspec-review] dispatching for '{change_name}'", err=True)

    system_prompt = build_review_prompt(change_name, repo_path, harness_agents_dir)
    user_prompt = (
        f"Review the OpenSpec change '{change_name}' — validate tasks, "
        f"run structural checks, perform semantic review, and archive if ready."
    )

    session_name = f"[action-harness] OpenSpec Review: {change_name} (repo: {worktree_path.name})"
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
        "--name",
        session_name,
    ]
    if model is not None:
        cmd.extend(["--model", model])
    if effort is not None:
        cmd.extend(["--effort", effort])
    if max_budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(max_budget_usd)])

    if verbose:
        typer.echo(f"  cwd: {worktree_path}", err=True)
        typer.echo(f"  cmd: {' '.join(cmd[:6])}...", err=True)

    start_time = time.monotonic()

    try:
        result = subprocess.run(
            cmd,
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=7200,
        )
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start_time
        error_msg = "OpenSpec review timed out after 7200s"
        typer.echo(f"[openspec-review] {error_msg}", err=True)
        return f'{{"error": "{error_msg}"}}', duration
    except (FileNotFoundError, OSError) as e:
        duration = time.monotonic() - start_time
        error_msg = f"Failed to launch openspec review: {e}"
        typer.echo(f"[openspec-review] {error_msg}", err=True)
        return f'{{"error": "{error_msg}"}}', duration

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
    except json.JSONDecodeError:
        return OpenSpecReviewResult(
            success=False,
            error="Failed to parse review output: invalid JSON from CLI",
            duration_seconds=duration,
        )

    # Check for dispatch-level error (timeout, launch failure)
    if "error" in output_data and "result" not in output_data:
        return OpenSpecReviewResult(
            success=False,
            error=str(output_data["error"]),
            duration_seconds=duration,
        )

    result_text = output_data.get("result", "")

    # Extract the JSON block from the result text
    review_data = extract_json_block(result_text)
    if review_data is None:
        return OpenSpecReviewResult(
            success=False,
            error="Failed to parse review output: no JSON block found in result",
            duration_seconds=duration,
        )

    status = review_data.get("status", "findings")
    findings = review_data.get("findings", [])

    return OpenSpecReviewResult(
        success=status in ("approved", "needs-human"),
        duration_seconds=duration,
        tasks_total=review_data.get("tasks_total", 0),
        tasks_complete=review_data.get("tasks_complete", 0),
        validation_passed=review_data.get("validation_passed", False),
        semantic_review_passed=review_data.get("semantic_review_passed", False),
        findings=findings if isinstance(findings, list) else [str(findings)],
        archived=review_data.get("archived", False),
        human_tasks_remaining=review_data.get("human_tasks_remaining", 0),
    )


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
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return False, "git push timed out after 120s"
    except (FileNotFoundError, OSError) as e:
        return False, f"git push failed: {e}"

    if push_result.returncode != 0:
        return False, f"git push failed: {push_result.stderr.strip()}"

    if verbose:
        typer.echo("[openspec-review] push succeeded", err=True)

    return True, None
