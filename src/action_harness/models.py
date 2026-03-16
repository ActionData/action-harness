"""Pydantic data models for action-harness."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from action_harness.profiler import RepoProfile


class ValidationError(Exception):
    """Raised when CLI input validation fails."""


class StageResult(BaseModel):
    """Base result type for all pipeline stages."""

    success: bool
    stage: str
    error: str | None = None
    duration_seconds: float | None = None


class WorktreeResult(StageResult):
    """Result from worktree creation."""

    stage: Literal["worktree"] = "worktree"
    worktree_path: Path | None = None
    branch: str = ""


class WorkerResult(StageResult):
    """Result from Claude Code worker dispatch."""

    stage: Literal["worker"] = "worker"
    commits_ahead: int = 0
    cost_usd: float | None = None
    worker_output: str | None = None
    session_id: str | None = None
    context_usage_pct: float | None = None


class EvalResult(StageResult):
    """Result from evaluation commands."""

    stage: Literal["eval"] = "eval"
    commands_run: int = 0
    commands_passed: int = 0
    failed_command: str | None = None
    feedback_prompt: str | None = None


class PrResult(StageResult):
    """Result from PR creation or pipeline-level failure."""

    stage: Literal["pr", "pipeline"] = "pr"
    pr_url: str | None = None
    branch: str = ""


class OpenSpecReviewResult(StageResult):
    """Result from OpenSpec review agent."""

    stage: Literal["openspec-review"] = "openspec-review"
    tasks_total: int = 0
    tasks_complete: int = 0
    validation_passed: bool = False
    semantic_review_passed: bool = False
    findings: list[str] = []
    archived: bool = False
    human_tasks_remaining: int = 0


class MergeResult(StageResult):
    """Result from the auto-merge stage.

    Success semantics: ``success=True`` means the stage ran without error,
    NOT that the PR was merged. A gate-blocked merge has ``success=True,
    merged=False``. Only ``success=False`` indicates the merge command
    itself failed (e.g. ``gh pr merge`` returned non-zero).
    """

    stage: Literal["merge"] = "merge"
    merged: bool = False
    merge_blocked_reason: str | None = None
    ci_passed: bool | None = None


class ReviewFinding(BaseModel):
    """A single finding from a review agent."""

    title: str
    file: str
    line: int | None = None
    severity: Literal["critical", "high", "medium", "low"]
    description: str
    agent: str


class AcknowledgedFinding(BaseModel):
    """A finding that was flagged but not fixed in a prior review round."""

    finding: ReviewFinding
    acknowledged_in_round: int


class ReviewResult(StageResult):
    """Result from a code review agent dispatch."""

    stage: Literal["review"] = "review"
    agent_name: str
    findings: list[ReviewFinding] = []
    cost_usd: float | None = None
    tolerance: str | None = None


# Discriminated union so Pydantic preserves subtypes through serialization.
# Only includes concrete stage types used in the pipeline (not the base StageResult).
StageResultUnion = Annotated[
    WorktreeResult
    | WorkerResult
    | EvalResult
    | PrResult
    | OpenSpecReviewResult
    | ReviewResult
    | MergeResult,
    Field(discriminator="stage"),
]


class RunManifest(BaseModel):
    """Complete record of a pipeline run, collecting all stage results."""

    change_name: str
    repo_path: str
    started_at: str
    completed_at: str
    success: bool
    stages: list[StageResultUnion]
    total_duration_seconds: float
    total_cost_usd: float | None = None
    retries: int = 0
    pr_url: str | None = None
    error: str | None = None
    manifest_path: str | None = None
    event_log_path: str | None = None
    needs_human: bool = False
    protected_files: list[str] = []
    profile: RepoProfile | None = None
