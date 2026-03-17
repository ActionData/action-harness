"""Checkpoint I/O for pipeline resume across process failures."""

import os
import tempfile
from pathlib import Path

import typer

from action_harness.models import PipelineCheckpoint

CHECKPOINTS_DIR = ".action-harness/checkpoints"


def write_checkpoint(repo_path: Path, checkpoint: PipelineCheckpoint) -> None:
    """Write a checkpoint file atomically (temp file + os.replace).

    Creates the checkpoints directory if needed.
    """
    checkpoints_dir = repo_path / CHECKPOINTS_DIR
    checkpoints_dir.mkdir(parents=True, exist_ok=True)

    target = checkpoints_dir / f"{checkpoint.run_id}.json"
    typer.echo(
        f"[checkpoint] writing checkpoint {checkpoint.run_id} "
        f"(stage: {checkpoint.completed_stage})",
        err=True,
    )

    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(checkpoints_dir), suffix=".tmp", prefix="checkpoint-"
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(checkpoint.model_dump_json(indent=2))
            os.replace(tmp_path, str(target))
        except BaseException:
            # Clean up temp file on any error
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as e:
        typer.echo(f"[checkpoint] error writing checkpoint: {e}", err=True)
        raise


def read_checkpoint(repo_path: Path, run_id: str) -> PipelineCheckpoint | None:
    """Read a checkpoint file. Returns None if file doesn't exist."""
    target = repo_path / CHECKPOINTS_DIR / f"{run_id}.json"
    typer.echo(f"[checkpoint] reading checkpoint {run_id}", err=True)

    if not target.exists():
        typer.echo(f"[checkpoint] checkpoint not found: {target}", err=True)
        return None

    try:
        raw = target.read_text(encoding="utf-8")
        return PipelineCheckpoint.model_validate_json(raw)
    except (OSError, UnicodeDecodeError) as e:
        typer.echo(f"[checkpoint] warning: failed to read checkpoint: {e}", err=True)
        return None
    except ValueError as e:
        typer.echo(f"[checkpoint] warning: failed to parse checkpoint: {e}", err=True)
        return None


def find_latest_checkpoint(
    repo_path: Path, change_name: str
) -> PipelineCheckpoint | None:
    """Find the most recent checkpoint for a given change name.

    Reads each .json file in .action-harness/checkpoints/, parses it, and
    compares checkpoint.change_name. Returns the most recent by timestamp.
    Returns None if no match.
    """
    checkpoints_dir = repo_path / CHECKPOINTS_DIR
    typer.echo(
        f"[checkpoint] scanning for latest checkpoint (change={change_name})",
        err=True,
    )

    if not checkpoints_dir.exists():
        typer.echo("[checkpoint] no checkpoints directory found", err=True)
        return None

    latest: PipelineCheckpoint | None = None
    latest_ts: str = ""

    try:
        for path in checkpoints_dir.iterdir():
            if not path.name.endswith(".json"):
                continue
            try:
                raw = path.read_text(encoding="utf-8")
                checkpoint = PipelineCheckpoint.model_validate_json(raw)
            except (OSError, UnicodeDecodeError, ValueError):
                continue

            if checkpoint.change_name != change_name:
                continue

            if latest is None or checkpoint.timestamp > latest_ts:
                latest = checkpoint
                latest_ts = checkpoint.timestamp
    except OSError as e:
        typer.echo(
            f"[checkpoint] warning: failed to scan checkpoints: {e}", err=True
        )
        return None

    if latest is not None:
        typer.echo(
            f"[checkpoint] found latest checkpoint: {latest.run_id}", err=True
        )
    else:
        typer.echo(
            f"[checkpoint] no checkpoints found for change '{change_name}'",
            err=True,
        )

    return latest


def delete_checkpoint(repo_path: Path, run_id: str) -> None:
    """Delete a checkpoint file. Logs warning if file doesn't exist (non-fatal)."""
    target = repo_path / CHECKPOINTS_DIR / f"{run_id}.json"
    typer.echo(f"[checkpoint] deleting checkpoint {run_id}", err=True)

    if not target.exists():
        typer.echo(
            f"[checkpoint] warning: checkpoint file not found for deletion: {target}",
            err=True,
        )
        return

    try:
        target.unlink()
        typer.echo(f"[checkpoint] deleted checkpoint {run_id}", err=True)
    except OSError as e:
        typer.echo(
            f"[checkpoint] warning: failed to delete checkpoint: {e}", err=True
        )
