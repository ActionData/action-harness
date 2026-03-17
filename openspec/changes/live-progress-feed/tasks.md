## 1. Event Log Tailing [no dependencies]

- [x] 1.1 Create `src/action_harness/progress_feed.py` with `tail_event_log(log_path: Path, callback: Callable[[PipelineEvent], bool], poll_interval: float = 1.0) -> None`. Opens the file, reads existing lines, then polls for new lines every `poll_interval` seconds. Parses each line as JSON into a `PipelineEvent` — skip lines that fail JSON parsing with a warning to stderr (handles partial writes during live tailing). Calls `callback(event)` for each event. Callback returns `True` to continue, `False` to stop (used for clean exit on `run.completed`). Handles `KeyboardInterrupt` for Ctrl+C.
- [x] 1.2 Add `find_latest_event_log(repo_path: Path) -> Path | None`. Scans `.action-harness/runs/` for `.events.jsonl` files, returns the most recently modified one, or None.
- [x] 1.3 Add `find_event_log_by_run_id(repo_path: Path, run_id: str) -> Path | None`. Looks for `.action-harness/runs/<run_id>.events.jsonl`, returns Path if exists, None otherwise.
- [x] 1.4 Add tests: `find_latest_event_log` with multiple log files returns most recent. Empty directory returns None. `find_event_log_by_run_id` with existing file returns path. Missing file returns None. `tail_event_log` with a pre-written file calls callback for each event.

## 2. Event Formatting [no dependencies]

- [x] 2.1 Add `format_event(event: PipelineEvent, start_time: datetime | None = None) -> str` to `progress_feed.py`. When `start_time` is available, format as `[MM:SS] event_name — details` using elapsed time. When `start_time` is None (no `run.started` seen), use wall-clock time from the event's `timestamp` field instead: `[HH:MM:SS] event_name — details`. Extract key details from `event.metadata` based on event type: `worker.completed` → commits_ahead + context_usage_pct, `eval.completed` → commands_passed/commands_run, `pr.created` → pr_url, review events → finding count, `run.completed` → success + duration_seconds. Note: `run.completed` does NOT have a `cost_usd` field — cost is on `worker.completed` events only.
- [x] 2.2 Add tests: format `worker.completed` event with metadata `commits_ahead=5, context_usage_pct=0.03` → output contains `5 commit(s)` and `3%`. Format `eval.completed` with `commands_passed=5, commands_run=5` → output contains `5/5 passed`. Format `run.completed` with `success=True` → output contains `success`.

## 3. CLI Command [depends: 1, 2]

- [ ] 3.1 Add `harness progress` command to `cli.py` with `--repo` (required Path), `--run` (optional str), `--json` (flag). Resolve the event log path via `find_latest_event_log` or `find_event_log_by_run_id`. If not found, print error and exit. Call `tail_event_log` with a callback that either prints formatted events or raw JSON lines.
- [ ] 3.2 The callback tracks `start_time` (from `run.started` event timestamp). On `run.completed` or `pipeline.error`, print summary and return `False` to exit the tail loop.
- [ ] 3.3 Update CLI docstring for the `progress` command.
- [ ] 3.4 Add tests: `--help` shows progress command. Command with no event logs prints "No event logs found". Command with `--run nonexistent` prints "Event log not found". `--json` test: write a 3-event test log file (`run.started`, `worker.completed`, `run.completed`), run progress with `--json`, assert stdout has exactly 3 lines, parse each as `PipelineEvent` via `model_validate_json()`, assert first event is `run.started` and last is `run.completed`.

## 4. Validation [depends: all]

- [ ] 4.1 Run `uv run pytest -v` — all tests pass
- [ ] 4.2 Run `uv run ruff check .` and `uv run mypy src/` — clean
