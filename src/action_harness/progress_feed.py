"""Live progress feed for pipeline observability.

Tails event log files and formats pipeline events for human-readable display.
"""

import json
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import typer
from pydantic import ValidationError

from action_harness.event_log import PipelineEvent


def tail_event_log(
    log_path: Path,
    callback: Callable[[PipelineEvent], bool],
    poll_interval: float = 1.0,
) -> None:
    """Tail an event log file, calling ``callback`` for each parsed event.

    Opens the file, reads existing lines, then polls for new lines every
    ``poll_interval`` seconds.  Each line is parsed as JSON into a
    ``PipelineEvent``.  Lines that fail JSON parsing are skipped with a
    warning to stderr (handles partial writes during live tailing).

    The callback receives each event and returns ``True`` to continue or
    ``False`` to stop (used for clean exit on ``run.completed``).

    Handles ``KeyboardInterrupt`` for Ctrl+C.
    """
    typer.echo(f"[progress] tailing {log_path}", err=True)
    try:
        with open(log_path) as fh:
            while True:
                line = fh.readline()
                if not line:
                    # No more data — poll for new lines
                    time.sleep(poll_interval)
                    continue

                line = line.strip()
                if not line:
                    continue

                try:
                    event = PipelineEvent.model_validate_json(line)
                except (json.JSONDecodeError, ValidationError) as exc:
                    typer.echo(
                        f"[progress] warning: skipping unparseable line: {exc}",
                        err=True,
                    )
                    continue

                should_continue = callback(event)
                if not should_continue:
                    return
    except KeyboardInterrupt:
        typer.echo("\n[progress] interrupted", err=True)
    except OSError as exc:
        typer.echo(f"[progress] error reading {log_path}: {exc}", err=True)


def find_latest_event_log(repo_path: Path) -> Path | None:
    """Find the most recently modified ``.events.jsonl`` file in a repo's runs directory.

    Scans ``.action-harness/runs/`` for ``.events.jsonl`` files and returns
    the most recently modified one, or ``None`` if none exist.
    """
    runs_dir = repo_path / ".action-harness" / "runs"
    typer.echo(f"[progress] scanning {runs_dir} for event logs", err=True)

    if not runs_dir.is_dir():
        typer.echo("[progress] runs directory does not exist", err=True)
        return None

    log_files = list(runs_dir.glob("*.events.jsonl"))
    if not log_files:
        typer.echo("[progress] no event log files found", err=True)
        return None

    latest = max(log_files, key=lambda p: p.stat().st_mtime)
    typer.echo(f"[progress] found latest: {latest.name}", err=True)
    return latest


def find_event_log_by_run_id(repo_path: Path, run_id: str) -> Path | None:
    """Find the event log for a specific run ID.

    Looks for ``.action-harness/runs/<run_id>.events.jsonl`` and returns
    the ``Path`` if it exists, ``None`` otherwise.
    """
    log_path = repo_path / ".action-harness" / "runs" / f"{run_id}.events.jsonl"
    typer.echo(f"[progress] looking for {log_path}", err=True)

    if log_path.is_file():
        typer.echo(f"[progress] found: {log_path.name}", err=True)
        return log_path

    typer.echo(f"[progress] not found: {log_path.name}", err=True)
    return None


def format_event(
    event: PipelineEvent,
    start_time: datetime | None = None,
) -> str:
    """Format a pipeline event for human-readable display.

    When ``start_time`` is available, format as ``[MM:SS] event — details``
    using elapsed time.  When ``start_time`` is ``None`` (no ``run.started``
    seen), use wall-clock time from the event's ``timestamp`` field instead:
    ``[HH:MM:SS] event — details``.
    """
    # Compute time prefix
    if start_time is not None:
        event_time = datetime.fromisoformat(event.timestamp)
        elapsed = event_time - start_time
        total_seconds = int(elapsed.total_seconds())
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        time_prefix = f"[{minutes:02d}:{seconds:02d}]"
    else:
        event_time = datetime.fromisoformat(event.timestamp)
        time_prefix = f"[{event_time.strftime('%H:%M:%S')}]"

    # Extract details based on event type
    details = _extract_details(event)

    if details:
        return f"{time_prefix} {event.event} — {details}"
    return f"{time_prefix} {event.event}"


def _extract_details(event: PipelineEvent) -> str:
    """Extract key details from event metadata based on event type."""
    meta = event.metadata
    parts: list[str] = []

    if event.event == "worker.completed":
        commits = meta.get("commits_ahead")
        if commits is not None:
            parts.append(f"{commits} commit(s)")
        ctx_pct = meta.get("context_usage_pct")
        if ctx_pct is not None:
            pct_display = int(float(ctx_pct) * 100)
            parts.append(f"context: {pct_display}%")

    elif event.event == "eval.completed":
        passed = meta.get("commands_passed")
        total = meta.get("commands_run")
        if passed is not None and total is not None:
            parts.append(f"{passed}/{total} passed")

    elif event.event == "pr.created":
        pr_url = meta.get("pr_url")
        if pr_url is not None:
            parts.append(str(pr_url))

    elif event.event in (
        "review.completed",
        "review_round.completed",
    ):
        finding_count = meta.get("finding_count")
        if finding_count is not None:
            parts.append(f"{finding_count} finding(s)")

    elif event.event == "run.completed":
        success = event.success if event.success is not None else meta.get("success")
        if success is not None:
            parts.append("success" if success else "failed")
        duration = (
            event.duration_seconds
            if event.duration_seconds is not None
            else meta.get("duration_seconds")
        )
        if duration is not None:
            parts.append(f"{float(duration):.0f}s")

    elif event.event == "run.started":
        change_name = meta.get("change_name")
        if change_name is not None:
            parts.append(str(change_name))
        repo = meta.get("repo_path")
        if repo is not None:
            parts.append(f"repo: {repo}")

    return ", ".join(parts)
