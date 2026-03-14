"""Structured event logging for pipeline observability.

Emits JSON-lines events to a per-run log file alongside the manifest.
Event emission is non-fatal: I/O errors are logged to stderr and swallowed.
"""

import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel, Field


class PipelineEvent(BaseModel):
    """A single structured pipeline event."""

    timestamp: str
    event: str
    run_id: str
    stage: str | None = None
    duration_seconds: float | None = None
    success: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventLogger:
    """Appends JSON-lines events to a per-run log file.

    Create one at the start of a pipeline run. Call ``emit()`` at stage
    boundaries. Call ``close()`` when the run finishes.
    """

    def __init__(self, log_path: Path, run_id: str) -> None:
        self.log_path = log_path
        self.run_id = run_id
        self._file: io.TextIOWrapper | None = None
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(log_path, "a")  # noqa: SIM115
        except (OSError, PermissionError) as e:
            typer.echo(f"[event_log] warning: failed to open log file: {e}", err=True)

    def emit(
        self,
        event: str,
        stage: str | None = None,
        duration_seconds: float | None = None,
        success: bool | None = None,
        **metadata: Any,
    ) -> None:
        """Write a single event as a JSON line. Never raises."""
        if self._file is None:
            return
        try:
            pe = PipelineEvent(
                timestamp=datetime.now(UTC).isoformat(),
                event=event,
                run_id=self.run_id,
                stage=stage,
                duration_seconds=duration_seconds,
                success=success,
                metadata=metadata,
            )
            self._file.write(pe.model_dump_json() + "\n")
            self._file.flush()
        except Exception as e:
            typer.echo(f"[event_log] warning: failed to emit event: {e}", err=True)

    def close(self) -> None:
        """Close the underlying file handle. No-op if already closed or never opened."""
        if self._file is not None and not self._file.closed:
            self._file.close()
