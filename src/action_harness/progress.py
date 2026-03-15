"""Progress file writing for retry context."""

from pathlib import Path

from action_harness.models import EvalResult, WorkerResult

PROGRESS_FILENAME = ".harness-progress.md"


def write_progress(
    worktree_path: Path,
    attempt: int,
    worker_result: WorkerResult,
    eval_result: EvalResult,
) -> None:
    """Append an attempt section to the progress file in the worktree.

    Creates the file with a header on first call. Appends a new
    ``## Attempt {N}`` section on each call. Also ensures the progress
    file is listed in the worktree's ``.gitignore``.
    """
    progress_file = worktree_path / PROGRESS_FILENAME

    # Ensure .gitignore excludes the progress file
    _ensure_gitignored(worktree_path)

    # Build the attempt section
    eval_status = "PASSED" if eval_result.success else "FAILED"
    lines: list[str] = [
        f"## Attempt {attempt}",
        f"- **Commits**: {worker_result.commits_ahead}",
        f"- **Eval result**: {eval_status}",
    ]
    if not eval_result.success and eval_result.feedback_prompt:
        lines.append(f"- **Feedback**: {eval_result.feedback_prompt}")
    lines.append(f"- **Duration**: {worker_result.duration_seconds}s")
    lines.append(f"- **Cost**: ${worker_result.cost_usd}")
    lines.append("")  # trailing newline after section

    section = "\n".join(lines) + "\n"

    if not progress_file.exists():
        progress_file.write_text(f"# Harness Progress\n\n{section}")
    else:
        with progress_file.open("a") as f:
            f.write(section)


def _ensure_gitignored(worktree_path: Path) -> None:
    """Add ``.harness-progress.md`` to ``.gitignore`` if not already present."""
    gitignore = worktree_path / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if PROGRESS_FILENAME in content:
            return
        with gitignore.open("a") as f:
            if not content.endswith("\n"):
                f.write("\n")
            f.write(f"{PROGRESS_FILENAME}\n")
    else:
        gitignore.write_text(f"{PROGRESS_FILENAME}\n")
