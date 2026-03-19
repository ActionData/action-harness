"""Claude Code CLI dispatch."""

import json
import subprocess
import time
from pathlib import Path

import typer

from action_harness.catalog.frequency import get_boosted_entries
from action_harness.catalog.loader import load_catalog
from action_harness.catalog.renderer import render_for_worker
from action_harness.models import WorkerResult
from action_harness.progress import PROGRESS_FILENAME

HARNESS_MD_FILENAME = "HARNESS.md"


def read_harness_md(worktree_path: Path) -> str | None:
    """Read HARNESS.md from the worktree root.

    Returns the file contents as a string, or None if the file is absent,
    empty, or contains only whitespace. Returns None and logs a warning
    on read errors (permissions, encoding) so an optional config file
    cannot crash the dispatch pipeline.
    """
    harness_md_path = worktree_path / HARNESS_MD_FILENAME
    if not harness_md_path.exists():
        return None
    try:
        contents = harness_md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        typer.echo(
            f"[worker] warning: could not read {harness_md_path}: {exc}",
            err=True,
        )
        return None
    if not contents.strip():
        return None
    typer.echo(
        f"[worker] loaded HARNESS.md ({len(contents)} chars) from {worktree_path}",
        err=True,
    )
    return contents


def build_system_prompt(change_name: str | None = None, harness_md: str | None = None) -> str:
    """Build the system prompt for a Claude Code worker.

    When change_name is provided, returns the OpenSpec-specific opsx-apply prompt.
    When change_name is None, returns a generic implementation prompt for freeform tasks.

    When harness_md is provided (read from a HARNESS.md file in the target repo),
    it is appended as a "Repo-Specific Instructions" section after the role instructions.

    Note: Worker prompts use the bare skill name (opsx-apply) not the plugin-
    namespaced form (action:opsx-apply). Workers run in target repo worktrees
    where skills are injected into .claude/skills/ without a plugin namespace.
    """
    if change_name is None:
        prompt = (
            "You are implementing a task in this repository. "
            "Make the requested changes, commit your work, and verify it works."
        )
    else:
        prompt = (
            f"You are implementing the OpenSpec change '{change_name}'. "
            f"Run the opsx-apply skill to implement all tasks for this change. "
            f"Commit your work incrementally as you complete each task. "
            f"After implementation, exercise the feature you built and report "
            f"what you tested and observed."
        )
    if harness_md is not None:
        prompt += f"\n\n## Repo-Specific Instructions\n\n{harness_md}"
    return prompt


def count_commits_ahead(worktree_path: Path, base_branch: str) -> int:
    """Count how many commits the worktree branch is ahead of the base branch."""
    result = subprocess.run(
        ["git", "rev-list", "--count", f"{base_branch}..HEAD"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        typer.echo(
            f"[worker] warning: git rev-list failed: {result.stderr.strip()}",
            err=True,
        )
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        typer.echo(
            f"[worker] warning: unexpected git rev-list output: {result.stdout.strip()}",
            err=True,
        )
        return 0


def dispatch_worker(
    change_name: str,
    worktree_path: Path,
    base_branch: str = "main",
    max_turns: int = 200,
    feedback: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    max_budget_usd: float | None = None,
    permission_mode: str = "bypassPermissions",
    verbose: bool = False,
    session_id: str | None = None,
    prompt: str | None = None,
    ecosystem: str = "unknown",
    repo_knowledge_dir: Path | None = None,
) -> WorkerResult:
    """Dispatch a Claude Code worker to implement a change.

    Invokes the claude CLI as a subprocess in the worktree directory.
    Captures JSON output and verifies the worker produced commits.

    When session_id is provided, resumes a prior session with --resume
    instead of starting fresh. Requires feedback to be set (raises ValueError
    if feedback is None). Omits --system-prompt on resume since the
    session already has it.

    Note: claude CLI availability is validated by cli.validate_inputs before
    the pipeline starts. This function assumes claude is in PATH.
    """
    if session_id is not None and feedback is None:
        msg = "resume requires feedback"
        raise ValueError(msg)

    resumed = session_id is not None
    if resumed:
        typer.echo(
            f"[worker] resuming session {session_id} for '{change_name}'",
            err=True,
        )
    else:
        typer.echo(f"[worker] dispatching for '{change_name}'", err=True)

    # Read progress file if it exists (provides retry context to the worker)
    progress_contents: str | None = None
    progress_file = worktree_path / PROGRESS_FILENAME
    if progress_file.exists():
        try:
            progress_contents = progress_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            typer.echo(
                f"[worker] warning: could not read progress file: {exc}",
                err=True,
            )

    if session_id is not None and feedback is not None:
        # Resume mode: feedback is the user prompt, no system prompt
        user_prompt: str = feedback
        if progress_contents:
            user_prompt = f"{progress_contents}\n\n{user_prompt}"
        session_name = f"[action-harness] Worker: {change_name} (repo: {worktree_path.name})"
        cmd = [
            "claude",
            "-p",
            user_prompt,
            "--resume",
            session_id,
            "--output-format",
            "json",
            "--max-turns",
            str(max_turns),
            "--permission-mode",
            permission_mode,
            "--name",
            session_name,
        ]
    else:
        # Fresh dispatch
        harness_md = read_harness_md(worktree_path)
        if prompt is not None:
            # Freeform prompt mode: generic system prompt, user's prompt as user prompt
            system_prompt = build_system_prompt(change_name=None, harness_md=harness_md)
            user_prompt = prompt
        else:
            # OpenSpec change mode: opsx-apply system prompt
            system_prompt = build_system_prompt(change_name, harness_md=harness_md)
            user_prompt = (
                f"Implement the OpenSpec change '{change_name}' using the opsx-apply skill."
            )

        # Inject catalog worker rules into the system prompt
        catalog_entries = load_catalog(ecosystem)
        boosted = (
            get_boosted_entries(repo_knowledge_dir, catalog_entries)
            if repo_knowledge_dir is not None
            else None
        )
        catalog_section = render_for_worker(catalog_entries, boosted=boosted)
        if catalog_section is not None:
            system_prompt = f"{system_prompt}\n\n{catalog_section}"
        if feedback:
            user_prompt = f"{user_prompt}\n\n{feedback}"
        if progress_contents:
            user_prompt = f"{progress_contents}\n\n{user_prompt}"
        session_name = (
            f"[action-harness] Worker: {change_name or 'freeform'} (repo: {worktree_path.name})"
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

    # Worker sessions routinely run 20-40 minutes; 7200s (2h) is a safety
    # net, not an expected bound. The 600s CLAUDE.md guideline is for CLI
    # tools like gh/git, not the core agent loop.
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
        typer.echo("[worker] timed out after 7200s", err=True)
        return WorkerResult(
            success=False,
            stage="worker",
            error="Claude CLI timed out after 7200s",
            duration_seconds=duration,
        )
    except (FileNotFoundError, OSError) as e:
        duration = time.monotonic() - start_time
        typer.echo(f"[worker] failed to launch: {e}", err=True)
        return WorkerResult(
            success=False,
            stage="worker",
            error=f"Failed to launch claude CLI: {e}",
            duration_seconds=duration,
        )

    duration = time.monotonic() - start_time

    # Parse JSON output
    cost_usd = None
    worker_output = None
    captured_session_id: str | None = None
    context_usage_pct: float | None = None
    if result.stdout:
        try:
            output_data = json.loads(result.stdout)
            cost_usd = output_data.get("cost_usd")
            worker_output = output_data.get("result")
            captured_session_id = output_data.get("session_id")

            # Compute context usage percentage from token counts
            usage = output_data.get("usage", {})
            model_usage = output_data.get("modelUsage", {})
            # model_info comes from json.loads output — values are JSON primitives
            model_info: dict[str, int] = next(iter(model_usage.values()), {}) if model_usage else {}
            context_window = int(model_info.get("contextWindow", 1_000_000))
            input_tokens = int(usage.get("input_tokens", 0))
            output_tokens = int(usage.get("output_tokens", 0))
            if context_window > 0:
                context_usage_pct = (input_tokens + output_tokens) / context_window
            else:
                typer.echo(
                    "[worker] warning: contextWindow is 0, cannot compute context usage",
                    err=True,
                )
        except json.JSONDecodeError:
            worker_output = result.stdout[:500]

    if result.returncode != 0:
        typer.echo(f"[worker] failed (exit {result.returncode})", err=True)
        return WorkerResult(
            success=False,
            stage="worker",
            error=f"Claude CLI exited with code {result.returncode}: {result.stderr[:500]}",
            duration_seconds=duration,
            cost_usd=cost_usd,
            worker_output=worker_output,
            session_id=captured_session_id,
            context_usage_pct=context_usage_pct,
        )

    # Check for commits against the base branch (provided by the pipeline from worktree creation)
    commits = count_commits_ahead(worktree_path, base_branch)

    if commits == 0:
        typer.echo("[worker] completed but produced no commits", err=True)
        return WorkerResult(
            success=False,
            stage="worker",
            error="No commits were produced. Review the change specs "
            "and implement the required tasks.",
            duration_seconds=duration,
            commits_ahead=0,
            cost_usd=cost_usd,
            worker_output=worker_output,
            session_id=captured_session_id,
            context_usage_pct=context_usage_pct,
        )

    typer.echo(
        f"[worker] completed: {commits} commit(s), ${cost_usd or '?'}",
        err=True,
    )
    return WorkerResult(
        success=True,
        stage="worker",
        duration_seconds=duration,
        commits_ahead=commits,
        cost_usd=cost_usd,
        worker_output=worker_output,
        session_id=captured_session_id,
        context_usage_pct=context_usage_pct,
    )
