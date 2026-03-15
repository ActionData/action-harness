"""Progress file writing for retry context."""

import subprocess
from pathlib import Path

import typer

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
    file is excluded from git via ``.git/info/exclude`` (local-only,
    never committed).
    """
    progress_file = worktree_path / PROGRESS_FILENAME
    typer.echo(f"[progress] writing attempt {attempt} to {progress_file}", err=True)

    # Ensure git excludes the progress file (local-only, not .gitignore)
    _ensure_git_excluded(worktree_path)

    # Build the attempt section
    eval_status = "PASSED" if eval_result.success else "FAILED"
    lines: list[str] = [
        f"## Attempt {attempt}",
        f"- **Commits**: {worker_result.commits_ahead}",
        f"- **Eval result**: {eval_status}",
    ]
    if not eval_result.success and eval_result.feedback_prompt:
        lines.append(f"- **Feedback**: {eval_result.feedback_prompt}")
    duration = worker_result.duration_seconds
    lines.append(f"- **Duration**: {f'{duration}s' if duration is not None else '?'}")
    cost = worker_result.cost_usd
    lines.append(f"- **Cost**: {f'${cost}' if cost is not None else '?'}")
    lines.append("")  # trailing newline after section

    section = "\n".join(lines) + "\n"

    if not progress_file.exists():
        progress_file.write_text(f"# Harness Progress\n\n{section}")
    else:
        with progress_file.open("a") as f:
            f.write(section)

    typer.echo(f"[progress] attempt {attempt} written", err=True)


def _ensure_git_excluded(worktree_path: Path) -> None:
    """Exclude ``.harness-progress.md`` via git's local exclude file.

    Uses ``.git/info/exclude`` (resolved via ``git rev-parse --git-dir``)
    so the exclusion is local-only and never committed. This avoids
    modifying the tracked ``.gitignore`` file, which would leak harness
    infrastructure into PRs.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            typer.echo("[progress] warning: git rev-parse failed, skipping exclude", err=True)
            return

        git_dir = Path(result.stdout.strip())
        if not git_dir.is_absolute():
            git_dir = worktree_path / git_dir

        exclude_file = git_dir / "info" / "exclude"
        exclude_file.parent.mkdir(parents=True, exist_ok=True)

        if exclude_file.exists():
            existing_lines = exclude_file.read_text().splitlines()
            if PROGRESS_FILENAME in existing_lines:
                return
            with exclude_file.open("a") as f:
                if existing_lines and existing_lines[-1] != "":
                    f.write("\n")
                f.write(f"{PROGRESS_FILENAME}\n")
        else:
            exclude_file.write_text(f"{PROGRESS_FILENAME}\n")
    except (OSError, subprocess.SubprocessError) as e:
        typer.echo(f"[progress] warning: failed to update git exclude: {e}", err=True)
