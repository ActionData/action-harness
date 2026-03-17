"""Tests for the `harness progress` CLI command."""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from action_harness.cli import app
from action_harness.event_log import EventLogger, PipelineEvent

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text for reliable assertions."""
    return _ANSI_RE.sub("", text)


class TestProgressHelp:
    def test_help_shows_progress_command(self) -> None:
        result = runner.invoke(app, ["progress", "--help"])
        output = _strip_ansi(result.output)
        assert "progress" in output.lower()
        assert "--repo" in output
        assert "--run" in output
        assert "--json" in output


class TestProgressNoLogs:
    def test_no_event_logs_prints_error(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["progress", "--repo", str(tmp_path)])
        assert result.exit_code != 0
        combined = _strip_ansi(result.output + (result.stderr or ""))
        assert "No event logs found" in combined

    def test_run_not_found_prints_error(self, tmp_path: Path) -> None:
        # Create the runs directory but no matching file
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)

        result = runner.invoke(app, ["progress", "--repo", str(tmp_path), "--run", "nonexistent"])
        assert result.exit_code != 0
        combined = _strip_ansi(result.output + (result.stderr or ""))
        assert "Event log not found" in combined


class TestProgressJson:
    @pytest.fixture
    def repo_with_events(self, tmp_path: Path) -> Path:
        """Create a repo with a 3-event log file."""
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)

        log_path = runs_dir / "test-run.events.jsonl"
        logger = EventLogger(log_path, "test-run")
        logger.emit("run.started", change_name="test-change", repo_path=str(tmp_path))
        logger.emit(
            "worker.completed",
            stage="worker",
            success=True,
            commits_ahead=3,
            context_usage_pct=0.05,
        )
        logger.emit("run.completed", success=True, duration_seconds=60.0)
        logger.close()
        return tmp_path

    def test_json_output_has_correct_events(self, repo_with_events: Path) -> None:
        result = runner.invoke(app, ["progress", "--repo", str(repo_with_events), "--json"])
        assert result.exit_code == 0

        # stdout should have exactly 3 JSON lines
        stdout_lines = [line for line in result.output.strip().splitlines() if line.strip()]
        # Filter out stderr diagnostic lines (they start with [progress])
        json_lines = [
            line
            for line in stdout_lines
            if not line.startswith("[progress]") and not line.startswith("\n[progress]")
        ]

        # Parse each line as PipelineEvent
        events: list[PipelineEvent] = []
        for line in json_lines:
            # Skip any stderr lines that leaked into output
            stripped = line.strip()
            if not stripped or stripped.startswith("["):
                continue
            event = PipelineEvent.model_validate_json(stripped)
            events.append(event)

        assert len(events) == 3
        assert events[0].event == "run.started"
        assert events[1].event == "worker.completed"
        assert events[2].event == "run.completed"

    def test_json_output_with_run_flag(self, repo_with_events: Path) -> None:
        result = runner.invoke(
            app, ["progress", "--repo", str(repo_with_events), "--run", "test-run", "--json"]
        )
        assert result.exit_code == 0

        json_lines = [
            line.strip()
            for line in result.output.strip().splitlines()
            if line.strip() and not line.strip().startswith("[")
        ]

        events: list[PipelineEvent] = []
        for line in json_lines:
            event = PipelineEvent.model_validate_json(line)
            events.append(event)

        assert len(events) == 3
        assert events[0].event == "run.started"
        assert events[2].event == "run.completed"


class TestProgressPipelineError:
    def test_pipeline_error_exits_with_code_1(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)

        log_path = runs_dir / "error-run.events.jsonl"
        logger = EventLogger(log_path, "error-run")
        logger.emit("run.started", change_name="test-change", repo_path=str(tmp_path))
        logger.emit("pipeline.error", error="eval timed out")
        logger.close()

        result = runner.invoke(app, ["progress", "--repo", str(tmp_path)])
        assert result.exit_code == 1

        output = _strip_ansi(result.output)
        assert "pipeline.error" in output


class TestProgressFormatted:
    def test_formatted_output_shows_events(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)

        log_path = runs_dir / "test-run.events.jsonl"
        logger = EventLogger(log_path, "test-run")
        logger.emit("run.started", change_name="test-change", repo_path=str(tmp_path))
        logger.emit("run.completed", success=True, duration_seconds=30.0)
        logger.close()

        result = runner.invoke(app, ["progress", "--repo", str(tmp_path)])
        assert result.exit_code == 0

        output = _strip_ansi(result.output)
        assert "run.started" in output
        assert "run.completed" in output
