## 1. Report Models [no dependencies]

- [x] 1.1 Create `src/action_harness/reporting.py` with Pydantic models: `RecurringFinding(title: str, count: int, files: str)`, `RecentRunSummary(change_name: str, success: bool, cost_usd: float | None, duration_seconds: float | None, date: str)`, `RunReport(total_runs: int, successful_runs: int, failed_runs: int, success_rate: float, failures_by_stage: dict[str, int], recurring_findings: list[RecurringFinding], catalog_frequency: dict[str, int], total_cost_usd: float | None, avg_duration_seconds: float | None, recent_runs: list[RecentRunSummary])`.
- [x] 1.2 Add tests: `RunReport` construction and `model_dump_json()` / `model_validate_json()` roundtrip. Assert specific field values survive: `result.total_runs == 5`, `result.failures_by_stage == {"eval": 2}`, `result.recurring_findings[0].count == 3`, `result.catalog_frequency["subprocess-timeout"] == 8`.

## 2. Manifest Loading [no dependencies]

- [x] 2.1 Add `load_manifests(repo_path: Path, since: str | None = None) -> list[RunManifest]` to `reporting.py`. Reads all `.json` files from `.action-harness/runs/` (excluding `.events.jsonl`), parses each as `RunManifest`, optionally filters by `started_at >= since`. Skip and warn on unparseable files.
- [x] 2.2 Add `parse_since(since: str) -> datetime | None` that handles relative durations with suffix `d` (days) or `h` (hours) — e.g., `7d`, `30d`, `24h` — and absolute ISO dates (`2026-03-15`). Returns None if parsing fails (with warning logged to stderr). When None is returned, `load_manifests` includes all manifests (no time filter).
- [x] 2.3 Add tests: load from directory with 3 manifests returns 3. Filter by `since` returns subset. Empty directory returns empty list. Malformed JSON skipped with warning. `.events.jsonl` files excluded.

## 3. Aggregation Logic [depends: 1, 2]

- [x] 3.1 Add `aggregate_report(manifests: list[RunManifest], catalog_frequency: dict[str, int] | None = None) -> RunReport`. Computes: success/failure counts and rate. Determine failure stage: find the last `StageResult` in `manifest.stages` where `success=False`. If no individual stage has `success=False` but `manifest.success=False`, count as stage `"pipeline"`. Sum cost across manifests (skip None; if all None, `total_cost_usd = None`). Average duration. Build recent runs list (last 10, most recent first).
- [x] 3.2 Add `group_recurring_findings(manifests: list[RunManifest]) -> list[RecurringFinding]`. Extracts all `ReviewFinding` objects from `ReviewResult` stages across manifests. Groups by title similarity using `_titles_overlap` imported from `action_harness.review_agents` (make it public by removing the underscore prefix — rename to `titles_overlap`). Returns list sorted by count descending.
- [x] 3.3 Add tests: 5 manifests (3 success, 2 fail) → correct rates. Failures at eval and review counted correctly. Recurring findings grouped across runs. Cost/duration aggregation handles None values. Empty manifest list returns zero report.

## 4. CLI Command [depends: 3]

- [ ] 4.1 Add `harness report` command to `cli.py` with `--repo` (required Path), `--since` (optional str), `--json` (flag), `--harness-home` (optional Path). Load manifests from `repo_path / ".action-harness" / "runs"`. Load catalog frequency from harness home: resolve via `_resolve_harness_home(harness_home)`, determine `repo_name` from repo path (use `repo_path.name` for local repos), read `harness_home / "repos" / repo_name / "knowledge" / "findings-frequency.json"` if it exists. The frequency file has nested structure `{entry_id: {"count": int, "last_seen": str}}` — extract `{entry_id: entry["count"]}` into a flat `dict[str, int]` before passing to `aggregate_report`. If the path doesn't exist (non-managed repo), pass `catalog_frequency=None`.
- [ ] 4.2 Terminal output: formatted summary with sections for success rate, failure stages, recurring findings, catalog frequency, recent runs. Use the format from the design doc.
- [ ] 4.3 `--json` output: `report.model_dump_json(indent=2)` to stdout, diagnostics to stderr.
- [ ] 4.4 Update CLI docstring for the `report` command.
- [ ] 4.5 Add tests: `--help` shows report command. Report with manifests produces output. `--json` produces valid JSON. `--since 7d` filters correctly. No manifests outputs "No runs found". Report with no harness home omits catalog section gracefully.

## 5. Validation [depends: all]

- [ ] 5.1 Run `uv run pytest -v` — all tests pass
- [ ] 5.2 Run `uv run ruff check .` and `uv run mypy src/` — clean
- [ ] 5.3 Run `harness report --repo .` and verify output shows data from actual runs in this repo
