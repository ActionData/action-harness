"""Tests for Pydantic result models."""

import json
from pathlib import Path

from action_harness.models import (
    EvalResult,
    PrResult,
    RunManifest,
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
        assert result.error is None
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
        assert result.error is None
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
        assert result.error is None
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
        assert result.feedback_prompt == "## Eval Failure\n..."


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
        assert result.error is None
        assert isinstance(result, StageResult)

    def test_failure(self) -> None:
        result = PrResult(success=False, stage="pr", error="push failed", branch="harness/foo")
        assert result.success is False
        assert result.error == "push failed"
        assert result.pr_url is None


class TestRunManifest:
    def test_success_manifest(self) -> None:
        stages: list[StageResult] = [
            WorktreeResult(
                success=True,
                stage="worktree",
                worktree_path=Path("/tmp/wt"),
                branch="harness/test",
                duration_seconds=1.5,
            ),
            WorkerResult(
                success=True,
                stage="worker",
                commits_ahead=2,
                cost_usd=0.15,
                duration_seconds=30.0,
            ),
            EvalResult(
                success=True,
                stage="eval",
                commands_run=4,
                commands_passed=4,
                duration_seconds=10.0,
            ),
            PrResult(
                success=True,
                stage="pr",
                pr_url="https://github.com/org/repo/pull/1",
                branch="harness/test",
                duration_seconds=2.0,
            ),
        ]
        manifest = RunManifest(
            change_name="test-feature",
            repo_path="/tmp/repo",
            started_at="2026-03-13T10:00:00+00:00",
            completed_at="2026-03-13T10:01:00+00:00",
            success=True,
            stages=stages,
            total_duration_seconds=60.0,
            total_cost_usd=0.15,
            pr_url="https://github.com/org/repo/pull/1",
        )
        assert manifest.success is True
        assert manifest.change_name == "test-feature"
        assert manifest.retries == 0
        assert manifest.error is None
        assert len(manifest.stages) == 4

    def test_failure_manifest(self) -> None:
        stages: list[StageResult] = [
            WorktreeResult(
                success=True,
                stage="worktree",
                worktree_path=Path("/tmp/wt"),
                branch="harness/test",
            ),
            WorkerResult(success=False, stage="worker", error="no commits produced"),
        ]
        manifest = RunManifest(
            change_name="test-feature",
            repo_path="/tmp/repo",
            started_at="2026-03-13T10:00:00+00:00",
            completed_at="2026-03-13T10:00:30+00:00",
            success=False,
            stages=stages,
            total_duration_seconds=30.0,
            retries=2,
            error="Worker failed: no commits produced",
        )
        assert manifest.success is False
        assert manifest.retries == 2
        assert manifest.error == "Worker failed: no commits produced"
        assert manifest.pr_url is None

    def test_model_dump_json_produces_valid_json(self) -> None:
        stages: list[StageResult] = [
            WorktreeResult(
                success=True,
                stage="worktree",
                worktree_path=Path("/tmp/wt"),
                branch="harness/test",
            ),
            WorkerResult(success=True, stage="worker", commits_ahead=1, cost_usd=0.10),
            EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4),
            PrResult(
                success=True,
                stage="pr",
                pr_url="https://github.com/org/repo/pull/1",
                branch="harness/test",
            ),
        ]
        manifest = RunManifest(
            change_name="test-feature",
            repo_path="/tmp/repo",
            started_at="2026-03-13T10:00:00+00:00",
            completed_at="2026-03-13T10:01:00+00:00",
            success=True,
            stages=stages,
            total_duration_seconds=60.0,
            total_cost_usd=0.10,
            pr_url="https://github.com/org/repo/pull/1",
        )
        json_str = manifest.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["change_name"] == "test-feature"
        assert parsed["success"] is True
        assert len(parsed["stages"]) == 4

    def test_stages_accepts_mixed_subtypes(self) -> None:
        stages: list[StageResult] = [
            WorktreeResult(success=True, stage="worktree", branch="harness/test"),
            WorkerResult(success=True, stage="worker", cost_usd=0.05),
            EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4),
            PrResult(success=True, stage="pr", branch="harness/test"),
        ]
        manifest = RunManifest(
            change_name="test",
            repo_path="/tmp/repo",
            started_at="2026-03-13T10:00:00+00:00",
            completed_at="2026-03-13T10:01:00+00:00",
            success=True,
            stages=stages,
            total_duration_seconds=60.0,
        )
        assert len(manifest.stages) == 4
        # Verify the list accepts all subtypes without error
        assert manifest.stages[0].stage == "worktree"
        assert manifest.stages[1].stage == "worker"
        assert manifest.stages[2].stage == "eval"
        assert manifest.stages[3].stage == "pr"
