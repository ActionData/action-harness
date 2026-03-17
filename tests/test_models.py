"""Tests for Pydantic result models."""

import json
from pathlib import Path

import pytest

from action_harness.models import (
    EvalResult,
    MergeResult,
    PipelineCheckpoint,
    PrResult,
    ReviewFinding,
    ReviewResult,
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

    def test_session_id_and_context_usage_roundtrip(self) -> None:
        result = WorkerResult(
            success=True,
            stage="worker",
            session_id="sess_abc123",
            context_usage_pct=0.45,
        )
        raw = result.model_dump_json()
        restored = WorkerResult.model_validate_json(raw)
        assert restored.session_id == "sess_abc123"
        assert restored.context_usage_pct == pytest.approx(0.45)

    def test_session_fields_default_none(self) -> None:
        result = WorkerResult(success=True, stage="worker")
        assert result.session_id is None
        assert result.context_usage_pct is None


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


class TestReviewFinding:
    def test_construction(self) -> None:
        finding = ReviewFinding(
            title="Bug found",
            file="src/foo.py",
            line=42,
            severity="high",
            description="Off-by-one error",
            agent="bug-hunter",
        )
        assert finding.title == "Bug found"
        assert finding.file == "src/foo.py"
        assert finding.line == 42
        assert finding.severity == "high"
        assert finding.description == "Off-by-one error"
        assert finding.agent == "bug-hunter"

    def test_line_optional(self) -> None:
        finding = ReviewFinding(
            title="Test gap",
            file="src/bar.py",
            severity="medium",
            description="Missing test",
            agent="test-reviewer",
        )
        assert finding.line is None

    def test_serialization_roundtrip(self) -> None:
        finding = ReviewFinding(
            title="Quality issue",
            file="src/baz.py",
            line=10,
            severity="low",
            description="Naming convention",
            agent="quality-reviewer",
        )
        raw = finding.model_dump_json()
        restored = ReviewFinding.model_validate_json(raw)
        assert restored.title == finding.title
        assert restored.severity == finding.severity
        assert restored.agent == finding.agent


class TestReviewResult:
    def test_success_with_findings(self) -> None:
        finding = ReviewFinding(
            title="Bug",
            file="foo.py",
            severity="high",
            description="desc",
            agent="bug-hunter",
        )
        result = ReviewResult(
            success=True,
            agent_name="bug-hunter",
            findings=[finding],
            cost_usd=0.05,
        )
        assert result.stage == "review"
        assert result.agent_name == "bug-hunter"
        assert len(result.findings) == 1
        assert result.cost_usd == 0.05
        assert isinstance(result, StageResult)

    def test_failure_result(self) -> None:
        result = ReviewResult(
            success=False,
            agent_name="test-reviewer",
            error="parse failure",
        )
        assert result.success is False
        assert result.error == "parse failure"
        assert result.findings == []
        assert result.cost_usd is None

    def test_serialization_roundtrip(self) -> None:
        finding = ReviewFinding(
            title="Issue",
            file="x.py",
            severity="critical",
            description="crash",
            agent="bug-hunter",
        )
        result = ReviewResult(
            success=True,
            agent_name="bug-hunter",
            findings=[finding],
            cost_usd=0.12,
            duration_seconds=5.0,
        )
        raw = result.model_dump_json()
        restored = ReviewResult.model_validate_json(raw)
        assert restored.agent_name == "bug-hunter"
        assert len(restored.findings) == 1
        assert restored.findings[0].title == "Issue"
        assert restored.cost_usd == 0.12

    def test_in_run_manifest(self) -> None:
        finding = ReviewFinding(
            title="test",
            file="foo.py",
            severity="high",
            description="desc",
            agent="bug-hunter",
        )
        review = ReviewResult(success=True, agent_name="bug-hunter", findings=[finding])
        manifest = RunManifest(
            change_name="test",
            repo_path=".",
            started_at="2026-01-01T00:00:00+00:00",
            completed_at="2026-01-01T00:00:01+00:00",
            success=True,
            stages=[review],
            total_duration_seconds=1.0,
        )
        raw = manifest.model_dump_json()
        restored = RunManifest.model_validate_json(raw)
        assert isinstance(restored.stages[0], ReviewResult)
        assert restored.stages[0].findings[0].title == "test"


class TestRunManifest:
    def _make_manifest(self, success: bool = True) -> RunManifest:
        stages: list[StageResult] = [
            WorktreeResult(
                success=True, stage="worktree", worktree_path=Path("/tmp/wt"), branch="harness/foo"
            ),
            WorkerResult(success=True, stage="worker", commits_ahead=2, cost_usd=0.15),
            EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4),
            PrResult(
                success=success,
                stage="pr",
                pr_url="https://github.com/org/repo/pull/1" if success else None,
                branch="harness/foo",
                error=None if success else "push failed",
            ),
        ]
        return RunManifest(
            change_name="test-change",
            repo_path="/tmp/repo",
            started_at="2026-01-01T00:00:00+00:00",
            completed_at="2026-01-01T00:01:30+00:00",
            success=success,
            stages=stages,
            total_duration_seconds=90.0,
            total_cost_usd=0.15,
            retries=0,
            pr_url="https://github.com/org/repo/pull/1" if success else None,
            error=None if success else "push failed",
        )

    def test_success_manifest(self) -> None:
        manifest = self._make_manifest(success=True)
        assert manifest.success is True
        assert manifest.pr_url == "https://github.com/org/repo/pull/1"
        assert manifest.error is None
        assert manifest.retries == 0
        assert len(manifest.stages) == 4
        assert manifest.total_cost_usd == 0.15

    def test_failure_manifest(self) -> None:
        manifest = self._make_manifest(success=False)
        assert manifest.success is False
        assert manifest.error == "push failed"
        assert manifest.pr_url is None

    def test_model_dump_json_produces_valid_json(self) -> None:
        manifest = self._make_manifest()
        raw = manifest.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["change_name"] == "test-change"
        assert parsed["success"] is True
        assert len(parsed["stages"]) == 4

    def test_model_validate_json_roundtrip(self) -> None:
        manifest = self._make_manifest()
        raw = manifest.model_dump_json()
        restored = RunManifest.model_validate_json(raw)
        assert restored.change_name == manifest.change_name
        assert restored.success == manifest.success
        assert len(restored.stages) == len(manifest.stages)
        # Verify subtype-specific fields survive roundtrip
        assert isinstance(restored.stages[0], WorktreeResult)
        assert restored.stages[0].branch == "harness/foo"
        assert isinstance(restored.stages[1], WorkerResult)
        assert restored.stages[1].cost_usd == 0.15
        assert restored.stages[1].commits_ahead == 2
        assert isinstance(restored.stages[2], EvalResult)
        assert restored.stages[2].commands_run == 4
        assert isinstance(restored.stages[3], PrResult)
        assert restored.stages[3].pr_url == "https://github.com/org/repo/pull/1"

    def test_stages_accept_mixed_subtypes(self) -> None:
        stages = [
            WorktreeResult(success=True, stage="worktree", branch="b"),
            WorkerResult(success=True, stage="worker", cost_usd=0.05),
            EvalResult(success=True, stage="eval", commands_run=1, commands_passed=1),
            PrResult(success=True, stage="pr", branch="b"),
        ]
        manifest = RunManifest(
            change_name="mixed",
            repo_path="/tmp",
            started_at="2026-01-01T00:00:00+00:00",
            completed_at="2026-01-01T00:00:01+00:00",
            success=True,
            stages=stages,
            total_duration_seconds=1.0,
        )
        assert len(manifest.stages) == 4

    def test_manifest_path_defaults_to_none(self) -> None:
        manifest = self._make_manifest()
        assert manifest.manifest_path is None

    def test_worker_result_session_fields_survive_manifest_roundtrip(self) -> None:
        stages = [
            WorktreeResult(success=True, stage="worktree", branch="b"),
            WorkerResult(
                success=True,
                stage="worker",
                commits_ahead=1,
                session_id="sess_abc123",
                context_usage_pct=0.45,
            ),
            EvalResult(success=True, stage="eval", commands_run=1, commands_passed=1),
            PrResult(success=True, stage="pr", branch="b"),
        ]
        manifest = RunManifest(
            change_name="test",
            repo_path="/tmp",
            started_at="2026-01-01T00:00:00+00:00",
            completed_at="2026-01-01T00:00:01+00:00",
            success=True,
            stages=stages,
            total_duration_seconds=1.0,
        )
        raw = manifest.model_dump_json()
        restored = RunManifest.model_validate_json(raw)
        worker = restored.stages[1]
        assert isinstance(worker, WorkerResult)
        assert worker.session_id == "sess_abc123"
        assert worker.context_usage_pct == pytest.approx(0.45)


class TestPipelineCheckpoint:
    def test_construction(self) -> None:
        checkpoint = PipelineCheckpoint(
            run_id="2026-01-01T00-00-00_00-00-test-change",
            change_name="test-change",
            repo_path="/tmp/repo",
            completed_stage="worktree",
            worktree_path="/tmp/wt",
            branch="harness/test-change",
            branch_head_sha="abc123",
            session_id="sess-123",
            timestamp="2026-01-01T00:00:00+00:00",
            ecosystem="python",
            auto_merge=True,
            skip_review=False,
            review_cycle=["low", "med"],
        )
        assert checkpoint.run_id == "2026-01-01T00-00-00_00-00-test-change"
        assert checkpoint.change_name == "test-change"
        assert checkpoint.completed_stage == "worktree"
        assert checkpoint.worktree_path == "/tmp/wt"
        assert checkpoint.branch == "harness/test-change"
        assert checkpoint.branch_head_sha == "abc123"
        assert checkpoint.session_id == "sess-123"
        assert checkpoint.ecosystem == "python"
        assert checkpoint.auto_merge is True
        assert checkpoint.skip_review is False
        assert checkpoint.review_cycle == ["low", "med"]
        assert checkpoint.protected_files == []
        assert checkpoint.stages == []
        assert checkpoint.last_worker_result is None
        assert checkpoint.last_eval_result is None
        assert checkpoint.pr_url is None

    def test_roundtrip_with_nested_stages(self) -> None:
        worker = WorkerResult(
            success=True,
            stage="worker",
            commits_ahead=3,
            cost_usd=0.42,
            session_id="sess-123",
            context_usage_pct=0.45,
        )
        eval_res = EvalResult(
            success=True,
            stage="eval",
            commands_run=4,
            commands_passed=4,
        )
        wt = WorktreeResult(
            success=True,
            stage="worktree",
            worktree_path=Path("/tmp/wt"),
            branch="harness/test-change",
        )
        checkpoint = PipelineCheckpoint(
            run_id="run-123",
            change_name="test-change",
            repo_path="/tmp/repo",
            completed_stage="worker_eval",
            worktree_path="/tmp/wt",
            branch="harness/test-change",
            branch_head_sha="deadbeef",
            session_id="sess-123",
            last_worker_result=worker,
            last_eval_result=eval_res,
            stages=[wt, worker, eval_res],
            timestamp="2026-01-01T00:00:00+00:00",
            ecosystem="python",
            auto_merge=True,
            review_cycle=["low", "high"],
        )
        raw = checkpoint.model_dump_json()
        restored = PipelineCheckpoint.model_validate_json(raw)
        assert restored.session_id == "sess-123"
        assert restored.completed_stage == "worker_eval"
        assert restored.auto_merge is True
        assert restored.review_cycle == ["low", "high"]
        assert len(restored.stages) == 3
        assert isinstance(restored.stages[0], WorktreeResult)
        assert restored.stages[0].worktree_path == Path("/tmp/wt")
        assert isinstance(restored.stages[1], WorkerResult)
        assert restored.stages[1].cost_usd == pytest.approx(0.42)
        assert restored.stages[1].session_id == "sess-123"
        assert isinstance(restored.stages[2], EvalResult)
        assert restored.stages[2].commands_run == 4
        assert restored.last_worker_result is not None
        assert restored.last_worker_result.session_id == "sess-123"
        assert restored.last_eval_result is not None
        assert restored.last_eval_result.commands_passed == 4

    def test_defaults(self) -> None:
        checkpoint = PipelineCheckpoint(
            run_id="run-1",
            change_name="c",
            repo_path="/r",
            completed_stage="worktree",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        assert checkpoint.worktree_path is None
        assert checkpoint.branch is None
        assert checkpoint.branch_head_sha is None
        assert checkpoint.pr_url is None
        assert checkpoint.session_id is None
        assert checkpoint.ecosystem == "unknown"
        assert checkpoint.auto_merge is False
        assert checkpoint.skip_review is False
        assert checkpoint.review_cycle is None

    def test_invalid_completed_stage_rejected(self) -> None:
        with pytest.raises(Exception):  # noqa: B017 — Pydantic ValidationError
            PipelineCheckpoint(
                run_id="run-1",
                change_name="c",
                repo_path="/r",
                completed_stage="typo_stage",  # type: ignore[arg-type]
                timestamp="2026-01-01T00:00:00+00:00",
            )


class TestMergeResult:
    def test_success_merged(self) -> None:
        result = MergeResult(success=True, merged=True)
        assert result.stage == "merge"
        assert result.success is True
        assert result.merged is True
        assert result.merge_blocked_reason is None
        assert result.ci_passed is None
        assert isinstance(result, StageResult)

    def test_blocked(self) -> None:
        result = MergeResult(
            success=True,
            merged=False,
            merge_blocked_reason="Protected files touched: CLAUDE.md",
        )
        assert result.success is True
        assert result.merged is False
        assert result.merge_blocked_reason == "Protected files touched: CLAUDE.md"

    def test_failed(self) -> None:
        result = MergeResult(success=False, merged=False, error="gh pr merge failed")
        assert result.success is False
        assert result.merged is False
        assert result.error == "gh pr merge failed"

    def test_roundtrip_through_run_manifest(self) -> None:
        merge = MergeResult(success=True, merged=True)
        stages = [
            WorktreeResult(success=True, stage="worktree", branch="b"),
            WorkerResult(success=True, stage="worker", commits_ahead=1),
            EvalResult(success=True, stage="eval", commands_run=1, commands_passed=1),
            PrResult(success=True, stage="pr", branch="b"),
            merge,
        ]
        manifest = RunManifest(
            change_name="test",
            repo_path=".",
            started_at="2026-01-01T00:00:00+00:00",
            completed_at="2026-01-01T00:00:01+00:00",
            success=True,
            stages=stages,
            total_duration_seconds=1.0,
        )
        raw = manifest.model_dump_json()
        restored = RunManifest.model_validate_json(raw)
        assert type(restored.stages[-1]) is MergeResult
        assert restored.stages[-1].merged is True
        assert restored.stages[-1].merge_blocked_reason is None
