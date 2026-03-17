"""Tests for the live progress feed module."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from action_harness.event_log import EventLogger, PipelineEvent
from action_harness.progress_feed import (
    find_event_log_by_run_id,
    find_latest_event_log,
    format_event,
    tail_event_log,
)


class TestFindLatestEventLog:
    def test_returns_most_recent_with_multiple_files(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)

        # Create two log files with different modification times.
        # Uses explicit mtime to avoid sleep-based flakiness.
        older = runs_dir / "old-run.events.jsonl"
        newer = runs_dir / "new-run.events.jsonl"
        older.write_text('{"event": "old"}\n')
        newer.write_text('{"event": "new"}\n')
        os.utime(older, (1000.0, 1000.0))
        os.utime(newer, (2000.0, 2000.0))

        result = find_latest_event_log(tmp_path)
        if result is None:
            raise ValueError("Expected a Path, got None")
        assert result.name == "new-run.events.jsonl"

    def test_returns_none_for_empty_directory(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)

        result = find_latest_event_log(tmp_path)
        assert result is None

    def test_returns_none_when_runs_dir_missing(self, tmp_path: Path) -> None:
        result = find_latest_event_log(tmp_path)
        assert result is None


class TestFindEventLogByRunId:
    def test_returns_path_when_file_exists(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)

        log_file = runs_dir / "my-run-id.events.jsonl"
        log_file.write_text('{"event": "test"}\n')

        result = find_event_log_by_run_id(tmp_path, "my-run-id")
        if result is None:
            raise ValueError("Expected a Path, got None")
        assert result == log_file

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)

        result = find_event_log_by_run_id(tmp_path, "nonexistent")
        assert result is None

    def test_returns_none_when_runs_dir_missing(self, tmp_path: Path) -> None:
        result = find_event_log_by_run_id(tmp_path, "nonexistent")
        assert result is None

    def test_rejects_path_traversal_run_id(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)

        result = find_event_log_by_run_id(tmp_path, "../../etc/passwd")
        assert result is None


class TestTailEventLog:
    def test_calls_callback_for_each_event(self, tmp_path: Path) -> None:
        """Write a complete log file, then tail it — callback sees all events."""
        log_path = tmp_path / "test.events.jsonl"
        logger = EventLogger(log_path, "test-run")
        logger.emit("run.started", change_name="test")
        logger.emit("worker.completed", commits_ahead=3)
        logger.emit("run.completed", success=True)
        logger.close()

        events: list[PipelineEvent] = []

        def collect(event: PipelineEvent) -> bool:
            events.append(event)
            return event.event != "run.completed"

        result = tail_event_log(log_path, collect, poll_interval=0.01, idle_timeout=0.5)

        assert result is True
        assert len(events) == 3
        assert events[0].event == "run.started"
        assert events[1].event == "worker.completed"
        assert events[2].event == "run.completed"

    def test_skips_unparseable_lines(self, tmp_path: Path) -> None:
        """Non-JSON lines are skipped, valid events still processed."""
        log_path = tmp_path / "test.events.jsonl"

        event = PipelineEvent(
            timestamp="2026-03-16T10:00:00+00:00",
            event="run.completed",
            run_id="test-run",
            success=True,
        )
        log_path.write_text(f"not-json-garbage\n{event.model_dump_json()}\n")

        events: list[PipelineEvent] = []

        def collect(ev: PipelineEvent) -> bool:
            events.append(ev)
            return ev.event != "run.completed"

        tail_event_log(log_path, collect, poll_interval=0.01, idle_timeout=0.5)

        assert len(events) == 1
        assert events[0].event == "run.completed"

    def test_returns_true_on_callback_stop(self, tmp_path: Path) -> None:
        """Callback returning False means normal exit → returns True."""
        log_path = tmp_path / "test.events.jsonl"
        logger = EventLogger(log_path, "test-run")
        logger.emit("run.completed", success=True)
        logger.close()

        result = tail_event_log(
            log_path,
            lambda ev: False,
            poll_interval=0.01,
            idle_timeout=0.5,
        )
        assert result is True

    def test_returns_false_on_idle_timeout(self, tmp_path: Path) -> None:
        """No terminal event + stale file mtime → idle timeout → returns False."""
        log_path = tmp_path / "test.events.jsonl"
        logger = EventLogger(log_path, "test-run")
        logger.emit("run.started", change_name="test")
        logger.close()

        # Set mtime far in the past so idle_timeout triggers immediately
        os.utime(log_path, (1000.0, 1000.0))

        events: list[PipelineEvent] = []
        result = tail_event_log(
            log_path,
            lambda ev: events.append(ev) is None,  # always returns True
            poll_interval=0.05,
            idle_timeout=1.0,
        )

        assert result is False
        assert len(events) == 1
        assert events[0].event == "run.started"

    def test_empty_file_exits_on_idle_timeout(self, tmp_path: Path) -> None:
        """Empty event log (created but not written to) exits via idle timeout."""
        log_path = tmp_path / "test.events.jsonl"
        log_path.write_text("")

        # Set mtime far in the past so idle_timeout triggers immediately
        os.utime(log_path, (1000.0, 1000.0))

        events: list[PipelineEvent] = []
        result = tail_event_log(
            log_path,
            lambda ev: events.append(ev) is None,
            poll_interval=0.05,
            idle_timeout=1.0,
        )

        assert result is False
        assert len(events) == 0


class TestFormatEvent:
    def test_worker_completed_with_metadata(self) -> None:
        event = PipelineEvent(
            timestamp="2026-03-16T10:00:30+00:00",
            event="worker.completed",
            run_id="test-run",
            metadata={"commits_ahead": 5, "context_usage_pct": 0.03},
        )
        start_time = datetime(2026, 3, 16, 10, 0, 0, tzinfo=UTC)
        result = format_event(event, start_time)

        assert "5 commit(s)" in result
        assert "3%" in result
        assert "[00:30]" in result

    def test_eval_completed_with_metadata(self) -> None:
        event = PipelineEvent(
            timestamp="2026-03-16T10:00:42+00:00",
            event="eval.completed",
            run_id="test-run",
            metadata={"commands_passed": 5, "commands_run": 5},
        )
        start_time = datetime(2026, 3, 16, 10, 0, 0, tzinfo=UTC)
        result = format_event(event, start_time)

        assert "5/5 passed" in result
        assert "[00:42]" in result

    def test_run_completed_success(self) -> None:
        event = PipelineEvent(
            timestamp="2026-03-16T10:02:31+00:00",
            event="run.completed",
            run_id="test-run",
            success=True,
            duration_seconds=151.0,
        )
        start_time = datetime(2026, 3, 16, 10, 0, 0, tzinfo=UTC)
        result = format_event(event, start_time)

        assert "success" in result
        assert "151s" in result
        assert "[02:31]" in result

    def test_run_completed_failure(self) -> None:
        event = PipelineEvent(
            timestamp="2026-03-16T10:02:31+00:00",
            event="run.completed",
            run_id="test-run",
            success=False,
            duration_seconds=90.0,
        )
        start_time = datetime(2026, 3, 16, 10, 0, 0, tzinfo=UTC)
        result = format_event(event, start_time)

        assert "failed" in result
        assert "90s" in result

    def test_fallback_to_wall_clock_when_no_start_time(self) -> None:
        event = PipelineEvent(
            timestamp="2026-03-16T14:30:00+00:00",
            event="worker.completed",
            run_id="test-run",
            metadata={"commits_ahead": 2, "context_usage_pct": 0.10},
        )
        result = format_event(event, start_time=None)

        assert "[14:30:00]" in result
        assert "2 commit(s)" in result
        assert "10%" in result

    def test_pr_created_shows_url(self) -> None:
        event = PipelineEvent(
            timestamp="2026-03-16T10:00:42+00:00",
            event="pr.created",
            run_id="test-run",
            metadata={"pr_url": "https://github.com/org/repo/pull/44"},
        )
        start_time = datetime(2026, 3, 16, 10, 0, 0, tzinfo=UTC)
        result = format_event(event, start_time)

        assert "https://github.com/org/repo/pull/44" in result

    def test_review_completed_shows_finding_count(self) -> None:
        event = PipelineEvent(
            timestamp="2026-03-16T10:01:15+00:00",
            event="review.completed",
            run_id="test-run",
            metadata={"finding_count": 17},
        )
        start_time = datetime(2026, 3, 16, 10, 0, 0, tzinfo=UTC)
        result = format_event(event, start_time)

        assert "17 finding(s)" in result
        assert "[01:15]" in result

    def test_review_round_completed_shows_finding_count(self) -> None:
        event = PipelineEvent(
            timestamp="2026-03-16T10:01:45+00:00",
            event="review_round.completed",
            run_id="test-run",
            metadata={"finding_count": 12},
        )
        start_time = datetime(2026, 3, 16, 10, 0, 0, tzinfo=UTC)
        result = format_event(event, start_time)

        assert "12 finding(s)" in result

    def test_pipeline_error_shows_error_message(self) -> None:
        event = PipelineEvent(
            timestamp="2026-03-16T10:00:45+00:00",
            event="pipeline.error",
            run_id="test-run",
            metadata={"error": "eval timed out"},
        )
        start_time = datetime(2026, 3, 16, 10, 0, 0, tzinfo=UTC)
        result = format_event(event, start_time)

        assert "eval timed out" in result
        assert "pipeline.error" in result

    def test_run_started_shows_change_name(self) -> None:
        event = PipelineEvent(
            timestamp="2026-03-16T10:00:00+00:00",
            event="run.started",
            run_id="test-run",
            metadata={"change_name": "my-change", "repo_path": "/tmp/repo"},
        )
        start_time = datetime(2026, 3, 16, 10, 0, 0, tzinfo=UTC)
        result = format_event(event, start_time)

        assert "my-change" in result
        assert "repo: /tmp/repo" in result

    def test_unknown_event_type_shows_name_only(self) -> None:
        event = PipelineEvent(
            timestamp="2026-03-16T10:00:10+00:00",
            event="some.future.event",
            run_id="test-run",
            metadata={"key": "value"},
        )
        start_time = datetime(2026, 3, 16, 10, 0, 0, tzinfo=UTC)
        result = format_event(event, start_time)

        assert "[00:10] some.future.event" == result
        assert "—" not in result

    def test_negative_elapsed_time_clamped_to_zero(self) -> None:
        """Events before start_time show [00:00] instead of negative time."""
        start = datetime(2026, 3, 16, 10, 0, 30, tzinfo=UTC)
        event = PipelineEvent(
            timestamp="2026-03-16T10:00:00+00:00",
            event="worker.completed",
            run_id="test-run",
            metadata={"commits_ahead": 1, "context_usage_pct": 0.01},
        )
        result = format_event(event, start)

        assert "[00:00]" in result
        assert "-" not in result.split("]")[0]

    def test_elapsed_time_calculation(self) -> None:
        start = datetime(2026, 3, 16, 10, 0, 0, tzinfo=UTC)
        event_time = start + timedelta(minutes=5, seconds=30)
        event = PipelineEvent(
            timestamp=event_time.isoformat(),
            event="eval.completed",
            run_id="test-run",
            metadata={"commands_passed": 3, "commands_run": 3},
        )
        result = format_event(event, start)

        assert "[05:30]" in result
