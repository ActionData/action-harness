"""Run manifest aggregation and failure reporting."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer
from pydantic import BaseModel

from action_harness.models import ReviewFinding, ReviewResult, RunManifest, RunStats


class RecurringFinding(BaseModel):
    """A review finding that recurred across multiple runs."""

    title: str
    count: int
    files: str


class RecentRunSummary(BaseModel):
    """Summary of a single run for the recent-runs section."""

    change_name: str
    success: bool
    cost_usd: float | None
    duration_seconds: float | None
    date: str


class RunReport(BaseModel):
    """Aggregate report across multiple pipeline runs."""

    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    failures_by_stage: dict[str, int]
    recurring_findings: list[RecurringFinding]
    catalog_frequency: dict[str, int]
    total_cost_usd: float | None
    avg_duration_seconds: float | None
    recent_runs: list[RecentRunSummary]


def parse_since(since: str) -> datetime | None:
    """Parse a --since value into a datetime.

    Handles relative durations with suffix ``d`` (days) or ``h`` (hours)
    — e.g., ``7d``, ``30d``, ``24h`` — and absolute ISO dates (``2026-03-15``).
    Returns None if parsing fails (with warning logged to stderr).
    """
    typer.echo(f"[report] parsing --since '{since}'", err=True)

    # Relative duration: e.g. 7d, 30d, 24h
    match = re.fullmatch(r"(\d+)([dh])", since.strip())
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        if unit == "d":
            result = datetime.now(UTC) - timedelta(days=value)
        else:
            result = datetime.now(UTC) - timedelta(hours=value)
        typer.echo(f"[report] --since resolved to {result.isoformat()}", err=True)
        return result

    # Absolute ISO date: e.g. 2026-03-15
    try:
        result = datetime.fromisoformat(since.strip())
        # If no timezone, assume UTC
        if result.tzinfo is None:
            result = result.replace(tzinfo=UTC)
        typer.echo(f"[report] --since resolved to {result.isoformat()}", err=True)
        return result
    except ValueError:
        pass

    typer.echo(
        f"[report] warning: could not parse --since '{since}' "
        "(expected e.g. 7d, 24h, or 2026-03-15)",
        err=True,
    )
    return None


def load_manifests(
    repo_path: Path,
    since: str | None = None,
    runs_dir: Path | None = None,
) -> list[RunManifest]:
    """Load all run manifests from a repository.

    When ``runs_dir`` is provided (managed repos), reads from that directory.
    Otherwise falls back to ``.action-harness/runs/`` inside ``repo_path``
    (local repos).

    Reads all ``.json`` files (excluding ``.events.jsonl``), parses each as
    ``RunManifest``, optionally filters by ``started_at >= since``. Skips and
    warns on unparseable files.
    """
    if runs_dir is None:
        runs_dir = repo_path / ".action-harness" / "runs"
    typer.echo(f"[report] loading manifests from {runs_dir}", err=True)

    if not runs_dir.is_dir():
        typer.echo("[report] no runs directory found", err=True)
        return []

    since_dt: datetime | None = None
    if since is not None:
        since_dt = parse_since(since)

    manifests: list[RunManifest] = []
    for path in sorted(runs_dir.iterdir()):
        # Only .json files, skip .events.jsonl
        if not path.name.endswith(".json"):
            continue
        if path.name.endswith(".events.jsonl"):
            continue

        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            typer.echo(f"[report] warning: could not read {path.name}: {e}", err=True)
            continue

        try:
            manifest = RunManifest.model_validate_json(raw)
        except Exception as e:
            typer.echo(f"[report] warning: could not parse {path.name}: {e}", err=True)
            continue

        # Filter by since
        if since_dt is not None:
            try:
                started = datetime.fromisoformat(manifest.started_at)
                if started.tzinfo is None:
                    started = started.replace(tzinfo=UTC)
                if started < since_dt:
                    continue
            except ValueError:
                # Can't parse timestamp — include the manifest
                pass

        manifests.append(manifest)

    typer.echo(f"[report] loaded {len(manifests)} manifest(s)", err=True)
    return manifests


def compute_run_stats(manifests: list[RunManifest]) -> RunStats:
    """Compute success/failure counts and success rate from manifests.

    Shared by ``aggregate_report`` and ``_gather_recent_runs`` in ``lead.py``
    to avoid duplicating the counting logic.
    """
    total = len(manifests)
    passed = sum(1 for m in manifests if m.success)
    failed = total - passed
    success_rate = (passed / total * 100.0) if total > 0 else 0.0
    return RunStats(passed=passed, failed=failed, total=total, success_rate=success_rate)


def group_recurring_findings(
    manifests: list[RunManifest],
) -> list[RecurringFinding]:
    """Group review findings across runs by title similarity.

    Extracts all ``ReviewFinding`` objects from ``ReviewResult`` stages
    across manifests. Groups by title similarity using ``titles_overlap``
    from ``action_harness.review_agents``. Returns list sorted by count
    descending.
    """
    from action_harness.review_agents import titles_overlap

    # Collect all findings across all manifests
    all_findings: list[ReviewFinding] = []
    for manifest in manifests:
        for stage in manifest.stages:
            if isinstance(stage, ReviewResult):
                all_findings.extend(stage.findings)

    if not all_findings:
        return []

    # Group by title similarity. O(n²) pairwise comparison — acceptable for
    # typical manifest counts (hundreds of findings). If this becomes a
    # bottleneck, consider pre-bucketing by normalized title tokens.
    groups: list[list[ReviewFinding]] = []
    assigned: list[bool] = [False] * len(all_findings)

    for i, finding in enumerate(all_findings):
        if assigned[i]:
            continue
        group = [finding]
        assigned[i] = True
        for j in range(i + 1, len(all_findings)):
            if assigned[j]:
                continue
            if titles_overlap(finding.title, all_findings[j].title):
                group.append(all_findings[j])
                assigned[j] = True
        groups.append(group)

    # Build RecurringFinding list
    result: list[RecurringFinding] = []
    for group in groups:
        title = group[0].title
        count = len(group)
        files = ", ".join(sorted({f.file for f in group}))
        result.append(RecurringFinding(title=title, count=count, files=files))

    # Sort by count descending
    result.sort(key=lambda r: r.count, reverse=True)
    return result


def aggregate_report(
    manifests: list[RunManifest],
    catalog_frequency: dict[str, int] | None = None,
) -> RunReport:
    """Aggregate manifests into a RunReport.

    Computes success/failure counts and rate. Determines failure stage by
    finding the last ``StageResult`` with ``success=False``. Sums cost
    across manifests. Averages duration. Builds recent runs list (last 10,
    most recent first).
    """
    stats = compute_run_stats(manifests)

    # Failure stages
    failures_by_stage: dict[str, int] = {}
    for manifest in manifests:
        if manifest.success:
            continue
        # Find last failed stage
        failed_stage: str | None = None
        for stage in manifest.stages:
            if not stage.success:
                failed_stage = stage.stage
        if failed_stage is None:
            # manifest.success=False but no individual stage failed
            failed_stage = "pipeline"
        failures_by_stage[failed_stage] = failures_by_stage.get(failed_stage, 0) + 1

    # Recurring findings
    recurring = group_recurring_findings(manifests)

    # Cost aggregation
    costs: list[float] = []
    for m in manifests:
        if m.total_cost_usd is not None:
            costs.append(m.total_cost_usd)
    total_cost: float | None = sum(costs) if costs else None

    # Duration aggregation — excludes zero-duration manifests (which indicate
    # incomplete or instantly-failed runs) to avoid skewing the average.
    durations: list[float] = [
        m.total_duration_seconds for m in manifests if m.total_duration_seconds > 0
    ]
    avg_duration: float | None = (sum(durations) / len(durations)) if durations else None

    # Recent runs (last 10, most recent first).
    # Parse to datetime for correct ordering across timezone offsets.
    def _parse_started_at(m: RunManifest) -> datetime:
        try:
            dt = datetime.fromisoformat(m.started_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            return datetime.min.replace(tzinfo=UTC)

    sorted_manifests = sorted(manifests, key=_parse_started_at, reverse=True)
    recent: list[RecentRunSummary] = []
    for m in sorted_manifests[:10]:
        # Extract date from started_at
        try:
            dt = datetime.fromisoformat(m.started_at)
            date_str = dt.strftime("%Y-%m-%d")
        except ValueError:
            date_str = m.started_at[:10] if len(m.started_at) >= 10 else m.started_at
        recent.append(
            RecentRunSummary(
                change_name=m.change_name,
                success=m.success,
                cost_usd=m.total_cost_usd,
                duration_seconds=m.total_duration_seconds,
                date=date_str,
            )
        )

    return RunReport(
        total_runs=stats.total,
        successful_runs=stats.passed,
        failed_runs=stats.failed,
        success_rate=stats.success_rate,
        failures_by_stage=failures_by_stage,
        recurring_findings=recurring,
        catalog_frequency=catalog_frequency or {},
        total_cost_usd=total_cost,
        avg_duration_seconds=avg_duration,
        recent_runs=recent,
    )
