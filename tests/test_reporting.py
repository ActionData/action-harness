"""Tests for run manifest aggregation and failure reporting."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from action_harness.cli import app
from action_harness.models import (
    EvalResult,
    ReviewFinding,
    ReviewResult,
    RunManifest,
    StageResultUnion,
    WorkerResult,
    WorktreeResult,
)
from action_harness.reporting import (
    RecentRunSummary,
    RecurringFinding,
    RunReport,
    aggregate_report,
    group_recurring_findings,
    load_manifests,
    parse_since,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(
    change_name: str = "test-change",
    success: bool = True,
    started_at: str = "2026-03-16T10:00:00+00:00",
    cost_usd: float | None = 1.50,
    duration: float = 120.0,
    stages: list[StageResultUnion] | None = None,
) -> RunManifest:
    """Create a minimal RunManifest for testing."""
    if stages is None:
        stages_list: list[StageResultUnion] = [
            WorktreeResult(success=True, worktree_path=Path("/tmp/wt")),
            WorkerResult(success=True, cost_usd=cost_usd),
            EvalResult(success=success, commands_run=3, commands_passed=3 if success else 2),
        ]
    else:
        stages_list = stages
    return RunManifest(
        change_name=change_name,
        repo_path="/tmp/repo",
        started_at=started_at,
        completed_at="2026-03-16T10:02:00+00:00",
        success=success,
        stages=stages_list,
        total_duration_seconds=duration,
        total_cost_usd=cost_usd,
    )


# ---------------------------------------------------------------------------
# 1.2 — Model construction and roundtrip
# ---------------------------------------------------------------------------


class TestRunReportModels:
    """RunReport construction and serialization roundtrip."""

    def test_construction_and_roundtrip(self) -> None:
        report = RunReport(
            total_runs=5,
            successful_runs=3,
            failed_runs=2,
            success_rate=60.0,
            failures_by_stage={"eval": 2},
            recurring_findings=[
                RecurringFinding(title="subprocess timeout", count=3, files="a.py, b.py"),
            ],
            catalog_frequency={"subprocess-timeout": 8},
            total_cost_usd=12.50,
            avg_duration_seconds=300.0,
            recent_runs=[
                RecentRunSummary(
                    change_name="fix-bug",
                    success=True,
                    cost_usd=2.50,
                    duration_seconds=120.0,
                    date="2026-03-16",
                ),
            ],
        )
        json_str = report.model_dump_json()
        restored = RunReport.model_validate_json(json_str)

        assert restored.total_runs == 5
        assert restored.failures_by_stage == {"eval": 2}
        assert restored.recurring_findings[0].count == 3
        assert restored.catalog_frequency["subprocess-timeout"] == 8
        assert restored.total_cost_usd == 12.50
        assert restored.avg_duration_seconds == 300.0
        assert restored.recent_runs[0].change_name == "fix-bug"

    def test_none_cost_and_duration(self) -> None:
        report = RunReport(
            total_runs=0,
            successful_runs=0,
            failed_runs=0,
            success_rate=0.0,
            failures_by_stage={},
            recurring_findings=[],
            catalog_frequency={},
            total_cost_usd=None,
            avg_duration_seconds=None,
            recent_runs=[],
        )
        json_str = report.model_dump_json()
        restored = RunReport.model_validate_json(json_str)
        assert restored.total_cost_usd is None
        assert restored.avg_duration_seconds is None


# ---------------------------------------------------------------------------
# 2.2 — parse_since
# ---------------------------------------------------------------------------


class TestParseSince:
    def test_relative_days(self) -> None:
        result = parse_since("7d")
        assert result is not None
        expected = datetime.now(UTC) - timedelta(days=7)
        # Allow 5s tolerance
        assert abs((result - expected).total_seconds()) < 5

    def test_relative_hours(self) -> None:
        result = parse_since("24h")
        assert result is not None
        expected = datetime.now(UTC) - timedelta(hours=24)
        assert abs((result - expected).total_seconds()) < 5

    def test_absolute_date(self) -> None:
        result = parse_since("2026-03-15")
        assert result is not None
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 15

    def test_invalid_returns_none(self) -> None:
        result = parse_since("not-a-date")
        assert result is None


# ---------------------------------------------------------------------------
# 2.3 — load_manifests
# ---------------------------------------------------------------------------


class TestLoadManifests:
    def test_load_from_directory(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)
        for i in range(3):
            m = _make_manifest(
                change_name=f"change-{i}",
                started_at=f"2026-03-{16 + i}T10:00:00+00:00",
            )
            (runs_dir / f"run-{i}.json").write_text(m.model_dump_json(), encoding="utf-8")

        result = load_manifests(tmp_path)
        assert len(result) == 3

    def test_filter_by_since(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)

        old = _make_manifest(started_at="2025-01-01T00:00:00+00:00")
        recent = _make_manifest(started_at="2026-03-16T10:00:00+00:00")
        (runs_dir / "old.json").write_text(old.model_dump_json(), encoding="utf-8")
        (runs_dir / "recent.json").write_text(recent.model_dump_json(), encoding="utf-8")

        result = load_manifests(tmp_path, since="2026-03-01")
        assert len(result) == 1
        assert result[0].started_at == "2026-03-16T10:00:00+00:00"

    def test_empty_directory(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)
        result = load_manifests(tmp_path)
        assert result == []

    def test_no_runs_directory(self, tmp_path: Path) -> None:
        result = load_manifests(tmp_path)
        assert result == []

    def test_malformed_json_skipped(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)
        (runs_dir / "bad.json").write_text("{invalid json", encoding="utf-8")
        good = _make_manifest()
        (runs_dir / "good.json").write_text(good.model_dump_json(), encoding="utf-8")

        result = load_manifests(tmp_path)
        assert len(result) == 1

    def test_events_jsonl_excluded(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)
        good = _make_manifest()
        (runs_dir / "run.json").write_text(good.model_dump_json(), encoding="utf-8")
        (runs_dir / "run.events.jsonl").write_text("{}\n{}\n", encoding="utf-8")

        result = load_manifests(tmp_path)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 3.1, 3.2, 3.3 — Aggregation
# ---------------------------------------------------------------------------


class TestAggregateReport:
    def test_basic_aggregation(self) -> None:
        manifests = [
            _make_manifest(success=True, cost_usd=1.0, duration=100.0),
            _make_manifest(success=True, cost_usd=2.0, duration=200.0),
            _make_manifest(success=True, cost_usd=3.0, duration=300.0),
            _make_manifest(
                success=False,
                cost_usd=0.5,
                duration=50.0,
                stages=[
                    WorktreeResult(success=True, worktree_path=Path("/tmp/wt")),
                    WorkerResult(success=True),
                    EvalResult(success=False, commands_run=3, commands_passed=1),
                ],
            ),
            _make_manifest(
                success=False,
                cost_usd=0.8,
                duration=80.0,
                stages=[
                    WorktreeResult(success=True, worktree_path=Path("/tmp/wt")),
                    WorkerResult(success=True),
                    EvalResult(success=False, commands_run=3, commands_passed=2),
                ],
            ),
        ]

        report = aggregate_report(manifests)
        assert report.total_runs == 5
        assert report.successful_runs == 3
        assert report.failed_runs == 2
        assert report.success_rate == 60.0
        assert report.failures_by_stage == {"eval": 2}
        assert report.avg_duration_seconds is not None
        expected_avg = (100.0 + 200.0 + 300.0 + 50.0 + 80.0) / 5
        assert report.avg_duration_seconds == expected_avg

    def test_failures_at_different_stages(self) -> None:
        manifests = [
            _make_manifest(
                success=False,
                stages=[
                    WorktreeResult(success=True, worktree_path=Path("/tmp/wt")),
                    WorkerResult(success=True),
                    EvalResult(success=False, commands_run=3, commands_passed=1),
                ],
            ),
            _make_manifest(
                success=False,
                stages=[
                    WorktreeResult(success=True, worktree_path=Path("/tmp/wt")),
                    WorkerResult(success=True),
                    EvalResult(success=True, commands_run=3, commands_passed=3),
                    ReviewResult(success=False, agent_name="bug-hunter"),
                ],
            ),
        ]

        report = aggregate_report(manifests)
        assert report.failures_by_stage["eval"] == 1
        assert report.failures_by_stage["review"] == 1

    def test_pipeline_stage_fallback(self) -> None:
        """When manifest.success=False but no stage has success=False."""
        manifests = [
            _make_manifest(
                success=False,
                stages=[
                    WorktreeResult(success=True, worktree_path=Path("/tmp/wt")),
                    WorkerResult(success=True),
                ],
            ),
        ]

        report = aggregate_report(manifests)
        assert report.failures_by_stage == {"pipeline": 1}

    def test_cost_none_handling(self) -> None:
        manifests = [
            _make_manifest(cost_usd=None),
            _make_manifest(cost_usd=None),
        ]
        report = aggregate_report(manifests)
        assert report.total_cost_usd is None

    def test_cost_partial_none(self) -> None:
        manifests = [
            _make_manifest(cost_usd=1.0),
            _make_manifest(cost_usd=None),
            _make_manifest(cost_usd=2.0),
        ]
        report = aggregate_report(manifests)
        assert report.total_cost_usd == 3.0

    def test_empty_manifests(self) -> None:
        report = aggregate_report([])
        assert report.total_runs == 0
        assert report.successful_runs == 0
        assert report.failed_runs == 0
        assert report.success_rate == 0.0
        assert report.failures_by_stage == {}
        assert report.recurring_findings == []
        assert report.total_cost_usd is None
        assert report.avg_duration_seconds is None

    def test_catalog_frequency_passed_through(self) -> None:
        freq = {"subprocess-timeout": 8, "bare-assert": 4}
        report = aggregate_report([], catalog_frequency=freq)
        assert report.catalog_frequency == freq

    def test_recent_runs_limit_10(self) -> None:
        manifests = [
            _make_manifest(
                change_name=f"change-{i}",
                started_at=f"2026-03-{10 + i:02d}T10:00:00+00:00",
            )
            for i in range(15)
        ]
        report = aggregate_report(manifests)
        assert len(report.recent_runs) == 10
        # Most recent first
        assert report.recent_runs[0].date == "2026-03-24"


class TestGroupRecurringFindings:
    def test_groups_similar_titles(self) -> None:
        manifests = [
            _make_manifest(
                stages=[
                    WorktreeResult(success=True, worktree_path=Path("/tmp/wt")),
                    ReviewResult(
                        success=True,
                        agent_name="bug-hunter",
                        findings=[
                            ReviewFinding(
                                title="subprocess.run missing timeout",
                                file="a.py",
                                severity="high",
                                description="desc",
                                agent="bug-hunter",
                            ),
                        ],
                    ),
                ],
            ),
            _make_manifest(
                stages=[
                    WorktreeResult(success=True, worktree_path=Path("/tmp/wt")),
                    ReviewResult(
                        success=True,
                        agent_name="quality-reviewer",
                        findings=[
                            ReviewFinding(
                                title="subprocess.run missing timeout parameter",
                                file="b.py",
                                severity="high",
                                description="desc",
                                agent="quality-reviewer",
                            ),
                        ],
                    ),
                ],
            ),
            _make_manifest(
                stages=[
                    WorktreeResult(success=True, worktree_path=Path("/tmp/wt")),
                    ReviewResult(
                        success=True,
                        agent_name="bug-hunter",
                        findings=[
                            ReviewFinding(
                                title="subprocess.run missing timeout",
                                file="c.py",
                                severity="high",
                                description="desc",
                                agent="bug-hunter",
                            ),
                        ],
                    ),
                ],
            ),
        ]

        result = group_recurring_findings(manifests)
        # All 3 should be grouped together (substring match)
        assert len(result) == 1
        assert result[0].count == 3

    def test_distinct_titles_not_grouped(self) -> None:
        manifests = [
            _make_manifest(
                stages=[
                    WorktreeResult(success=True, worktree_path=Path("/tmp/wt")),
                    ReviewResult(
                        success=True,
                        agent_name="bug-hunter",
                        findings=[
                            ReviewFinding(
                                title="subprocess.run missing timeout",
                                file="a.py",
                                severity="high",
                                description="desc",
                                agent="bug-hunter",
                            ),
                            ReviewFinding(
                                title="SQL injection in query builder",
                                file="b.py",
                                severity="critical",
                                description="desc",
                                agent="bug-hunter",
                            ),
                        ],
                    ),
                ],
            ),
        ]

        result = group_recurring_findings(manifests)
        assert len(result) == 2
        titles = {r.title for r in result}
        assert "subprocess.run missing timeout" in titles
        assert "SQL injection in query builder" in titles

    def test_no_findings(self) -> None:
        manifests = [_make_manifest()]
        result = group_recurring_findings(manifests)
        assert result == []


# ---------------------------------------------------------------------------
# 4.5 — CLI tests
# ---------------------------------------------------------------------------

_runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _init_git_repo(path: Path) -> None:
    """Create a bare .git directory so the path passes git repo validation."""
    (path / ".git").mkdir(exist_ok=True)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _extract_json(output: str) -> dict[str, object]:
    """Extract JSON block from CliRunner output (which mixes stdout/stderr)."""
    json_start = output.find("{\n")
    if json_start < 0:
        raise ValueError(f"No JSON found in output: {output[:200]}")
    json_end = output.rfind("}") + 1
    return json.loads(output[json_start:json_end])


class TestReportCLI:
    def test_help_shows_report(self) -> None:
        result = _runner.invoke(app, ["report", "--help"])
        assert result.exit_code == 0
        assert "report" in _strip_ansi(result.output).lower()

    def test_report_with_manifests(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)
        m = _make_manifest(success=True, cost_usd=1.50, duration=120.0)
        (runs_dir / "run-1.json").write_text(m.model_dump_json(), encoding="utf-8")

        result = _runner.invoke(app, ["report", "--repo", str(tmp_path)])
        output = _strip_ansi(result.output)
        assert "Success Rate" in output
        assert "1/1" in output

    def test_report_json_output(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)
        m = _make_manifest(success=True)
        (runs_dir / "run-1.json").write_text(m.model_dump_json(), encoding="utf-8")

        result = _runner.invoke(app, ["report", "--repo", str(tmp_path), "--json"])
        assert result.exit_code == 0
        parsed = _extract_json(result.output)
        assert parsed["total_runs"] == 1
        assert parsed["successful_runs"] == 1
        assert "success_rate" in parsed

    def test_since_filters(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)
        old = _make_manifest(started_at="2020-01-01T00:00:00+00:00")
        recent = _make_manifest(started_at="2026-03-16T10:00:00+00:00")
        (runs_dir / "old.json").write_text(old.model_dump_json(), encoding="utf-8")
        (runs_dir / "recent.json").write_text(recent.model_dump_json(), encoding="utf-8")

        result = _runner.invoke(app, ["report", "--repo", str(tmp_path), "--since", "7d", "--json"])
        assert result.exit_code == 0
        parsed = _extract_json(result.output)
        assert parsed["total_runs"] == 1

    def test_no_manifests(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        result = _runner.invoke(app, ["report", "--repo", str(tmp_path)])
        output = _strip_ansi(result.output)
        assert "No runs found" in output

    def test_non_git_repo_exits_with_error(self, tmp_path: Path) -> None:
        result = _runner.invoke(app, ["report", "--repo", str(tmp_path)])
        assert result.exit_code == 1
        assert "not a git repository" in _strip_ansi(result.output).lower()

    def test_catalog_frequency_loaded(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)
        m = _make_manifest()
        (runs_dir / "run.json").write_text(m.model_dump_json(), encoding="utf-8")

        fake_home = tmp_path / "fake-harness-home"
        repo_name = tmp_path.name
        freq_dir = fake_home / "repos" / repo_name / "knowledge"
        freq_dir.mkdir(parents=True)
        freq_data = {
            "subprocess-timeout": {"count": 8, "last_seen": "2026-03-16"},
            "bare-assert": {"count": 4, "last_seen": "2026-03-15"},
        }
        (freq_dir / "findings-frequency.json").write_text(json.dumps(freq_data), encoding="utf-8")

        result = _runner.invoke(
            app,
            ["report", "--repo", str(tmp_path), "--json", "--harness-home", str(fake_home)],
        )
        assert result.exit_code == 0
        parsed = _extract_json(result.output)
        assert parsed["catalog_frequency"] == {"subprocess-timeout": 8, "bare-assert": 4}

    def test_no_harness_home_omits_catalog(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        runs_dir = tmp_path / ".action-harness" / "runs"
        runs_dir.mkdir(parents=True)
        m = _make_manifest()
        (runs_dir / "run.json").write_text(m.model_dump_json(), encoding="utf-8")

        fake_home = tmp_path / "fake-harness-home"
        fake_home.mkdir()

        result = _runner.invoke(
            app,
            ["report", "--repo", str(tmp_path), "--json", "--harness-home", str(fake_home)],
        )
        assert result.exit_code == 0
        parsed = _extract_json(result.output)
        assert parsed["catalog_frequency"] == {}
