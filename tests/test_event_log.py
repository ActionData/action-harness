"""Tests for the structured event logging module."""

import json
from pathlib import Path
from unittest.mock import patch

from action_harness.event_log import EventLogger, PipelineEvent


class TestPipelineEvent:
    def test_serializes_to_valid_json_with_required_fields(self) -> None:
        event = PipelineEvent(
            timestamp="2026-03-13T10:00:00+00:00",
            event="run.started",
            run_id="2026-03-13T10-00-00_00-00-test",
        )
        raw = event.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["timestamp"] == "2026-03-13T10:00:00+00:00"
        assert parsed["event"] == "run.started"
        assert parsed["run_id"] == "2026-03-13T10-00-00_00-00-test"
        assert parsed["stage"] is None
        assert parsed["duration_seconds"] is None
        assert parsed["success"] is None
        assert parsed["metadata"] == {}

    def test_serializes_optional_fields(self) -> None:
        event = PipelineEvent(
            timestamp="2026-03-13T10:00:00+00:00",
            event="eval.completed",
            run_id="run-1",
            stage="eval",
            duration_seconds=1.5,
            success=True,
            metadata={"commands_passed": 4},
        )
        parsed = json.loads(event.model_dump_json())
        assert parsed["stage"] == "eval"
        assert parsed["duration_seconds"] == 1.5
        assert parsed["success"] is True
        assert parsed["metadata"]["commands_passed"] == 4


class TestEventLogger:
    def test_emit_writes_one_json_line_per_call(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.events.jsonl"
        logger = EventLogger(log_path, "run-1")

        logger.emit("run.started", change_name="test")
        logger.emit("run.completed", success=True)
        logger.close()

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "timestamp" in parsed
            assert "event" in parsed
            assert parsed["run_id"] == "run-1"

    def test_emit_does_not_raise_on_io_error(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.events.jsonl"
        logger = EventLogger(log_path, "run-1")

        # Force an I/O error by closing the file handle before emit
        logger._file.close()
        # Re-open as read-only won't work — just mock write to raise
        logger._file = open(log_path, "a")  # noqa: SIM115

        with patch.object(logger._file, "write", side_effect=OSError("disk full")):
            # Should not raise
            logger.emit("run.started")

    def test_close_closes_file_handle(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.events.jsonl"
        logger = EventLogger(log_path, "run-1")
        assert not logger._file.closed
        logger.close()
        assert logger._file.closed

    def test_close_is_noop_if_already_closed(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.events.jsonl"
        logger = EventLogger(log_path, "run-1")
        logger.close()
        logger.close()  # Should not raise
        assert logger._file.closed


class TestEventLoggerIntegration:
    def test_multi_event_roundtrip(self, tmp_path: Path) -> None:
        """Integration test: emit several events, read back, validate structure."""
        log_path = tmp_path / "runs" / "test.events.jsonl"
        logger = EventLogger(log_path, "integration-run")

        logger.emit("run.started", change_name="my-change", repo_path="/tmp/repo")
        logger.emit(
            "worktree.created",
            stage="worktree",
            branch="harness/my-change",
            worktree_path="/tmp/wt",
        )
        logger.emit("worker.dispatched", stage="worker", attempt=0)
        logger.emit(
            "worker.completed",
            stage="worker",
            duration_seconds=12.5,
            success=True,
            commits_ahead=3,
            cost_usd=0.15,
        )
        logger.emit("eval.started", stage="eval", command_count=4)
        logger.emit("eval.command.passed", stage="eval", command="uv run pytest -v")
        logger.emit(
            "eval.completed",
            stage="eval",
            success=True,
            commands_passed=4,
            commands_run=4,
        )
        logger.emit(
            "run.completed",
            success=True,
            duration_seconds=30.0,
            retries=0,
            error=None,
        )
        logger.close()

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 8

        expected_events = [
            "run.started",
            "worktree.created",
            "worker.dispatched",
            "worker.completed",
            "eval.started",
            "eval.command.passed",
            "eval.completed",
            "run.completed",
        ]

        for i, line in enumerate(lines):
            parsed = json.loads(line)
            assert "timestamp" in parsed
            assert "event" in parsed
            assert "run_id" in parsed
            assert parsed["run_id"] == "integration-run"
            assert parsed["event"] == expected_events[i]

        # Spot-check metadata
        started = json.loads(lines[0])
        assert started["metadata"]["change_name"] == "my-change"

        worker_done = json.loads(lines[3])
        assert worker_done["metadata"]["cost_usd"] == 0.15
        assert worker_done["duration_seconds"] == 12.5
        assert worker_done["success"] is True


class TestEventLoggerNonFatal:
    def test_io_error_logs_warning_and_continues(self, tmp_path: Path) -> None:
        """Emit with a broken file handle logs warning, does not raise."""
        log_path = tmp_path / "test.events.jsonl"
        logger = EventLogger(log_path, "run-1")

        with (
            patch.object(logger._file, "write", side_effect=OSError("disk full")),
            patch("action_harness.event_log.typer.echo") as mock_echo,
        ):
            logger.emit("run.started")

        mock_echo.assert_called_once()
        call_args = mock_echo.call_args
        assert "failed to emit event" in call_args[0][0]
        assert call_args[1]["err"] is True

        logger.close()
