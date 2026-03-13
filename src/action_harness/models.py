"""Pydantic data models for action-harness."""

from pathlib import Path

from pydantic import BaseModel


class StageResult(BaseModel):
    """Base result type for all pipeline stages."""

    success: bool
    stage: str
    error: str | None = None
    duration_seconds: float | None = None


class WorktreeResult(StageResult):
    """Result from worktree creation."""

    worktree_path: Path | None = None
    branch: str = ""


class WorkerResult(StageResult):
    """Result from Claude Code worker dispatch."""

    commits_ahead: int = 0
    cost_usd: float | None = None
    worker_output: str | None = None


class EvalResult(StageResult):
    """Result from evaluation commands."""

    commands_run: int = 0
    commands_passed: int = 0
    failed_command: str | None = None
    feedback_prompt: str | None = None


class PrResult(StageResult):
    """Result from PR creation."""

    pr_url: str | None = None
    branch: str = ""


class RunManifest(BaseModel):
    """Complete record of a pipeline run, collecting all stage results."""

    change_name: str
    repo_path: str
    started_at: str
    completed_at: str
    success: bool
    stages: list[StageResult]
    total_duration_seconds: float
    total_cost_usd: float | None = None
    retries: int = 0
    pr_url: str | None = None
    error: str | None = None
    manifest_path: str | None = None
