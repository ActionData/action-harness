"""Tests for Pydantic result models."""

from pathlib import Path

from action_harness.models import (
    EvalResult,
    PrResult,
    StageResult,
    WorkerResult,
    WorktreeResult,
)


class TestStageResult:
    def test_success_result(self) -> None:
        result = StageResult(success=True, stage="test")
        assert result.success is True
        assert result.stage == "test"
        assert result.error is None
        assert result.duration_seconds is None

    def test_failure_result(self) -> None:
        result = StageResult(success=False, stage="test", error="something broke")
        assert result.success is False
        assert result.error == "something broke"


class TestWorktreeResult:
    def test_success(self) -> None:
        result = WorktreeResult(
            success=True, stage="worktree", worktree_path=Path("/tmp/wt"), branch="harness/foo"
        )
        assert result.worktree_path == Path("/tmp/wt")
        assert result.branch == "harness/foo"
        assert isinstance(result, StageResult)

    def test_failure(self) -> None:
        result = WorktreeResult(success=False, stage="worktree", error="branch exists")
        assert result.success is False
        assert result.error == "branch exists"
        assert result.worktree_path is None


class TestWorkerResult:
    def test_success(self) -> None:
        result = WorkerResult(
            success=True, stage="worker", commits_ahead=3, cost_usd=0.12, worker_output="done"
        )
        assert result.commits_ahead == 3
        assert result.cost_usd == 0.12
        assert isinstance(result, StageResult)

    def test_failure(self) -> None:
        result = WorkerResult(success=False, stage="worker", error="no commits produced")
        assert result.success is False
        assert result.error == "no commits produced"
        assert result.commits_ahead == 0


class TestEvalResult:
    def test_success(self) -> None:
        result = EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4)
        assert result.commands_run == 4
        assert result.commands_passed == 4
        assert result.failed_command is None
        assert isinstance(result, StageResult)

    def test_failure(self) -> None:
        result = EvalResult(
            success=False,
            stage="eval",
            error="pytest failed",
            commands_run=2,
            commands_passed=1,
            failed_command="uv run pytest -v",
            feedback_prompt="## Eval Failure\n...",
        )
        assert result.success is False
        assert result.error == "pytest failed"
        assert result.failed_command == "uv run pytest -v"
        assert result.feedback_prompt is not None


class TestPrResult:
    def test_success(self) -> None:
        result = PrResult(
            success=True,
            stage="pr",
            pr_url="https://github.com/org/repo/pull/1",
            branch="harness/foo",
        )
        assert result.pr_url == "https://github.com/org/repo/pull/1"
        assert result.branch == "harness/foo"
        assert isinstance(result, StageResult)

    def test_failure(self) -> None:
        result = PrResult(success=False, stage="pr", error="push failed", branch="harness/foo")
        assert result.success is False
        assert result.error == "push failed"
        assert result.pr_url is None
