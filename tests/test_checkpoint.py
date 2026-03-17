"""Tests for checkpoint I/O operations."""

from pathlib import Path

from action_harness.checkpoint import (
    delete_checkpoint,
    find_latest_checkpoint,
    read_checkpoint,
    write_checkpoint,
)
from action_harness.models import (
    EvalResult,
    PipelineCheckpoint,
    WorkerResult,
    WorktreeResult,
)


def _make_checkpoint(
    run_id: str = "run-1",
    change_name: str = "test-change",
    timestamp: str = "2026-01-01T00:00:00+00:00",
    completed_stage: str = "worker_eval",
) -> PipelineCheckpoint:
    return PipelineCheckpoint(
        run_id=run_id,
        change_name=change_name,
        repo_path="/tmp/repo",
        completed_stage=completed_stage,
        worktree_path="/tmp/wt",
        branch="harness/test-change",
        branch_head_sha="abc123",
        session_id="sess_abc",
        stages=[
            WorktreeResult(success=True, stage="worktree", branch="harness/test-change"),
            WorkerResult(success=True, stage="worker", commits_ahead=2, session_id="sess_abc"),
        ],
        timestamp=timestamp,
        ecosystem="python",
    )


class TestWriteAndReadRoundtrip:
    def test_write_then_read(self, tmp_path: Path) -> None:
        checkpoint = _make_checkpoint()
        write_checkpoint(tmp_path, checkpoint)
        restored = read_checkpoint(tmp_path, "run-1")

        assert restored is not None
        assert restored.run_id == "run-1"
        assert restored.change_name == "test-change"
        assert restored.completed_stage == "worker_eval"
        assert restored.session_id == "sess_abc"
        assert len(restored.stages) == 2
        assert isinstance(restored.stages[0], WorktreeResult)
        assert isinstance(restored.stages[1], WorkerResult)
        assert restored.stages[1].session_id == "sess_abc"

    def test_write_creates_directory(self, tmp_path: Path) -> None:
        checkpoint = _make_checkpoint()
        write_checkpoint(tmp_path, checkpoint)
        checkpoints_dir = tmp_path / ".action-harness" / "checkpoints"
        assert checkpoints_dir.exists()
        assert (checkpoints_dir / "run-1.json").exists()

    def test_write_overwrites_existing(self, tmp_path: Path) -> None:
        cp1 = _make_checkpoint(timestamp="2026-01-01T00:00:00+00:00")
        cp2 = _make_checkpoint(timestamp="2026-01-01T01:00:00+00:00")
        write_checkpoint(tmp_path, cp1)
        write_checkpoint(tmp_path, cp2)
        restored = read_checkpoint(tmp_path, "run-1")
        assert restored is not None
        assert restored.timestamp == "2026-01-01T01:00:00+00:00"

    def test_atomic_write_no_partial_files(self, tmp_path: Path) -> None:
        checkpoint = _make_checkpoint()
        write_checkpoint(tmp_path, checkpoint)
        checkpoints_dir = tmp_path / ".action-harness" / "checkpoints"
        tmp_files = list(checkpoints_dir.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestReadCheckpoint:
    def test_read_nonexistent_returns_none(self, tmp_path: Path) -> None:
        result = read_checkpoint(tmp_path, "nonexistent")
        assert result is None

    def test_read_corrupt_json_returns_none(self, tmp_path: Path) -> None:
        checkpoints_dir = tmp_path / ".action-harness" / "checkpoints"
        checkpoints_dir.mkdir(parents=True)
        (checkpoints_dir / "bad.json").write_text("not json at all")
        result = read_checkpoint(tmp_path, "bad")
        assert result is None


class TestFindLatestCheckpoint:
    def test_finds_most_recent(self, tmp_path: Path) -> None:
        cp1 = _make_checkpoint(run_id="run-1", timestamp="2026-01-01T00:00:00+00:00")
        cp2 = _make_checkpoint(run_id="run-2", timestamp="2026-01-01T01:00:00+00:00")
        cp3 = _make_checkpoint(run_id="run-3", timestamp="2026-01-01T00:30:00+00:00")
        write_checkpoint(tmp_path, cp1)
        write_checkpoint(tmp_path, cp2)
        write_checkpoint(tmp_path, cp3)

        latest = find_latest_checkpoint(tmp_path, "test-change")
        assert latest is not None
        assert latest.run_id == "run-2"

    def test_filters_by_change_name(self, tmp_path: Path) -> None:
        cp1 = _make_checkpoint(
            run_id="run-a", change_name="change-a", timestamp="2026-01-01T02:00:00+00:00"
        )
        cp2 = _make_checkpoint(
            run_id="run-b", change_name="change-b", timestamp="2026-01-01T01:00:00+00:00"
        )
        write_checkpoint(tmp_path, cp1)
        write_checkpoint(tmp_path, cp2)

        result = find_latest_checkpoint(tmp_path, "change-b")
        assert result is not None
        assert result.run_id == "run-b"

    def test_no_matches_returns_none(self, tmp_path: Path) -> None:
        cp = _make_checkpoint(run_id="run-x", change_name="other-change")
        write_checkpoint(tmp_path, cp)
        result = find_latest_checkpoint(tmp_path, "nonexistent")
        assert result is None

    def test_no_checkpoints_dir_returns_none(self, tmp_path: Path) -> None:
        result = find_latest_checkpoint(tmp_path, "test-change")
        assert result is None


class TestDeleteCheckpoint:
    def test_delete_existing(self, tmp_path: Path) -> None:
        checkpoint = _make_checkpoint()
        write_checkpoint(tmp_path, checkpoint)
        target = tmp_path / ".action-harness" / "checkpoints" / "run-1.json"
        assert target.exists()
        delete_checkpoint(tmp_path, "run-1")
        assert not target.exists()

    def test_delete_nonexistent_no_error(self, tmp_path: Path) -> None:
        delete_checkpoint(tmp_path, "nonexistent")


class TestCheckpointWithNestedResults:
    def test_roundtrip_with_worker_and_eval(self, tmp_path: Path) -> None:
        worker = WorkerResult(
            success=True,
            stage="worker",
            commits_ahead=3,
            cost_usd=0.15,
            session_id="sess_xyz",
        )
        eval_res = EvalResult(
            success=True,
            stage="eval",
            commands_run=4,
            commands_passed=4,
        )
        checkpoint = PipelineCheckpoint(
            run_id="run-nested",
            change_name="test-change",
            repo_path=str(tmp_path),
            completed_stage="worker_eval",
            worktree_path="/tmp/wt",
            branch="harness/test-change",
            branch_head_sha="deadbeef",
            session_id="sess_xyz",
            last_worker_result=worker,
            last_eval_result=eval_res,
            stages=[
                WorktreeResult(success=True, stage="worktree", branch="harness/test-change"),
                worker,
                eval_res,
            ],
            timestamp="2026-01-01T00:00:00+00:00",
        )
        write_checkpoint(tmp_path, checkpoint)
        restored = read_checkpoint(tmp_path, "run-nested")

        assert restored is not None
        assert restored.last_worker_result is not None
        assert restored.last_worker_result.session_id == "sess_xyz"
        assert restored.last_eval_result is not None
        assert restored.last_eval_result.commands_passed == 4
        assert len(restored.stages) == 3
