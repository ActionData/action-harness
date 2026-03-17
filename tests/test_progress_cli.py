"""Tests for the `harness progress` CLI command."""

import re
from pathlib import Path

from typer.testing import CliRunner

from action_harness.cli import app
from action_harness.event_log import EventLogger, PipelineEvent

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text for reliable assertions."""
    return _ANSI_RE.sub("", text)


def _parse_json_events(output: str) -> list[PipelineEvent]:
    """Parse JSON events from stdout, filtering out any non-JSON lines."""
    events: list[PipelineEvent] = []
    for line in output.strip().splitlines():
        stripped = line.strip()
        if not stripped or not stripped.startswith("{"):
            continue
        events.append(PipelineEvent.model_validate_json(stripped))
    return events


def _make_repo_with_events(
    tmp_path: Path,
    run_id: str = "test-run",
    events: list[tuple[str, dict[str, object]]] | None = None,
) -> Path:
    """Create a repo with an event log. Returns the repo path."""
    runs_dir = tmp_path / ".action-harness" / "runs"
    runs_dir.mkdir(parents=True)
    log_path = runs_dir / f"{run_id}.events.jsonl"
    logger = EventLogger(log_path, run_id)

    if events is None:
        events = [
            ("run.started", {"change_name": "test-change", "repo_path": str(tmp_path)}),
            (
                "worker.completed",
                {"stage": "worker", "success": True, "commits_ahead": 3, "context_usage_pct": 0.05},
            ),
            ("run.completed", {"success": True, "duration_seconds": 60.0}),
        ]

    for event_name, kwargs in events:
        logger.emit(event_name, **kwargs)
    logger.close()
    return tmp_path


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
        assert "No event logs found" in _strip_ansi(result.output)

    def test_run_not_found_prints_error(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)

        result = runner.invoke(app, ["progress", "--repo", str(tmp_path), "--run", "nonexistent"])
        assert result.exit_code != 0
        assert "Event log not found" in _strip_ansi(result.output)

    def test_nonexistent_repo_path_prints_error(self, tmp_path: Path) -> None:
        bad_path = tmp_path / "does-not-exist"
        result = runner.invoke(app, ["progress", "--repo", str(bad_path)])
        assert result.exit_code != 0
        assert "does not exist" in _strip_ansi(result.output)


class TestProgressJson:
    def test_json_output_has_correct_events(self, tmp_path: Path) -> None:
        repo = _make_repo_with_events(tmp_path)
        result = runner.invoke(app, ["progress", "--repo", str(repo), "--json"])
        assert result.exit_code == 0

        events = _parse_json_events(result.output)
        assert len(events) == 3
        assert events[0].event == "run.started"
        assert events[1].event == "worker.completed"
        assert events[2].event == "run.completed"

    def test_json_output_with_run_flag(self, tmp_path: Path) -> None:
        repo = _make_repo_with_events(tmp_path, run_id="specific-run")
        result = runner.invoke(
            app, ["progress", "--repo", str(repo), "--run", "specific-run", "--json"]
        )
        assert result.exit_code == 0

        events = _parse_json_events(result.output)
        assert len(events) == 3
        assert events[0].event == "run.started"
        assert events[2].event == "run.completed"


class TestProgressPipelineError:
    def test_pipeline_error_exits_with_code_1(self, tmp_path: Path) -> None:
        repo = _make_repo_with_events(
            tmp_path,
            events=[
                ("run.started", {"change_name": "test-change", "repo_path": str(tmp_path)}),
                ("pipeline.error", {"error": "eval timed out"}),
            ],
        )

        result = runner.invoke(app, ["progress", "--repo", str(repo)])
        assert result.exit_code == 1

        output = _strip_ansi(result.output)
        assert "pipeline.error" in output

    def test_pipeline_error_formatted_shows_error_detail(self, tmp_path: Path) -> None:
        repo = _make_repo_with_events(
            tmp_path,
            events=[
                ("run.started", {"change_name": "test", "repo_path": str(tmp_path)}),
                ("pipeline.error", {"error": "worker crashed"}),
            ],
        )

        result = runner.invoke(app, ["progress", "--repo", str(repo)])
        output = _strip_ansi(result.output)
        assert "worker crashed" in output


class TestProgressFailedRun:
    def test_failed_run_exits_with_code_1(self, tmp_path: Path) -> None:
        repo = _make_repo_with_events(
            tmp_path,
            events=[
                ("run.started", {"change_name": "test", "repo_path": str(tmp_path)}),
                ("run.completed", {"success": False, "duration_seconds": 90.0}),
            ],
        )

        result = runner.invoke(app, ["progress", "--repo", str(repo)])
        assert result.exit_code == 1

        output = _strip_ansi(result.output)
        assert "failed" in output

    def test_successful_run_exits_with_code_0(self, tmp_path: Path) -> None:
        repo = _make_repo_with_events(tmp_path)

        result = runner.invoke(app, ["progress", "--repo", str(repo)])
        assert result.exit_code == 0


class TestProgressFormatted:
    def test_formatted_output_shows_events(self, tmp_path: Path) -> None:
        repo = _make_repo_with_events(tmp_path)

        result = runner.invoke(app, ["progress", "--repo", str(repo)])
        assert result.exit_code == 0

        output = _strip_ansi(result.output)
        assert "run.started" in output
        assert "run.completed" in output
