"""Shared test fixtures and helpers."""

import shutil
import subprocess
from pathlib import Path


def cleanup_worktrees(repo: Path) -> None:
    """Remove all worktrees registered with a repo and their temp directories.

    Prunes stale metadata, then force-removes each non-main worktree and its
    parent directory if it's an ah-* temp dir.
    """
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
    )
    list_result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
    )
    for line in list_result.stdout.splitlines():
        if line.startswith("worktree "):
            wt_path = Path(line.split(" ", 1)[1])
            if wt_path != repo:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(wt_path)],
                    cwd=repo,
                    capture_output=True,
                    timeout=30,
                )
                # Clean up parent temp directory
                parent = wt_path.parent
                if parent.name.startswith("ah-") and parent.exists():
                    shutil.rmtree(parent, ignore_errors=True)
