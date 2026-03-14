## 1. Event Model and Logger

- [ ] 1.1 Create `src/action_harness/event_log.py` with a `PipelineEvent` Pydantic model containing fields: `timestamp` (str), `event` (str), `run_id` (str), `stage` (str | None = None), `duration_seconds` (float | None = None), `success` (bool | None = None), `metadata` (dict[str, Any] with default_factory=dict).
- [ ] 1.2 In `event_log.py`, create an `EventLogger` class that takes `log_path: Path` and `run_id: str` in its constructor, opens the file for appending, and stores the file handle. Add a `close()` method that closes the file handle (no-op if already closed).
- [ ] 1.3 In `EventLogger`, implement `emit(self, event: str, stage: str | None = None, duration_seconds: float | None = None, success: bool | None = None, **metadata: Any) -> None` that: (a) constructs a `PipelineEvent` with `timestamp=datetime.now(UTC).isoformat()`, `run_id=self.run_id`, and the provided arguments with `metadata` from kwargs, (b) writes `event.model_dump_json() + "\n"` to the file, (c) calls `self._file.flush()` to ensure the line is written immediately, (d) wraps the entire body in try/except Exception and on error calls `typer.echo(f"[event_log] warning: failed to emit event: {e}", err=True)`.
- [ ] 1.4 Add unit tests in `tests/test_event_log.py`: test that `PipelineEvent` serializes to valid JSON with all required fields, test that `EventLogger.emit` writes one JSON-line per call, test that `EventLogger.emit` does not raise on I/O error (mock the file to raise OSError), test that `close()` closes the file handle.

## 2. Integrate Logger into Pipeline

- [ ] 2.1 In `src/action_harness/models.py`, add `event_log_path: str | None = None` field to `RunManifest`.
- [ ] 2.2 In `src/action_harness/pipeline.py`, import `EventLogger` from `event_log`. In `run_pipeline`, after computing `started_at`, generate `run_id` using `started_at` with the filesystem-safe transformation (replace colons with `-`, plus with `_`) plus `-{change_name}`. Also update `_write_manifest` to accept and use this pre-generated `run_id` for the manifest filename instead of computing its own from `completed_at`. This ensures the event log and manifest filenames match (spec requirement). Create the `.action-harness/runs/` directory. Compute `log_path = runs_dir / f"{run_id}.events.jsonl"`. Instantiate `EventLogger(log_path, run_id)`. Create the logger BEFORE the try block so it is available in except and finally.
- [ ] 2.3 In `run_pipeline`, emit `run.started` event with `metadata={"change_name": change_name, "repo_path": str(repo), "max_retries": max_retries}` immediately after creating the logger, BEFORE the try block.
- [ ] 2.4 In `run_pipeline`, use a `finally` block (after the try/except) to emit `run.completed` and close the logger. This ensures `run.completed` is always the last event, even on unexpected error. Emit with `success=pr_result.success`, `duration_seconds` computed from `started_at` to now, and `metadata={"retries": retries, "error": pr_result.error}`. Then call `logger.close()`.
- [ ] 2.5 In `run_pipeline`, in the `except Exception` handler, emit `pipeline.error` event with `metadata={"error": str(e)}` before constructing the `PrResult`.
- [ ] 2.6 Set `manifest.event_log_path = str(log_path)` on the manifest before writing it. Pass `run_id` to `_write_manifest` so it uses the same run_id for the manifest filename.
- [ ] 2.7 Pass the `EventLogger` instance into `_run_pipeline_inner` as a new parameter `logger: EventLogger`. Add it after `stages` in the parameter list to minimize diff noise.

## 3. Stage Events in Pipeline

- [ ] 3.1 In `_run_pipeline_inner`, after `create_worktree` returns: emit `worktree.created` (with `metadata={"branch": wt_result.branch, "worktree_path": str(wt_result.worktree_path)}`) on success, or `worktree.failed` (with `metadata={"error": wt_result.error}`) on failure. Both with `stage="worktree"`.
- [ ] 3.2 In `_run_pipeline_inner`, before calling `dispatch_worker`: emit `worker.dispatched` with `stage="worker"` and `metadata={"attempt": attempt}`.
- [ ] 3.3 In `_run_pipeline_inner`, after `dispatch_worker` returns: emit `worker.completed` (with `stage="worker"`, `duration_seconds=worker_result.duration_seconds`, `success=True`, `metadata={"commits_ahead": worker_result.commits_ahead, "cost_usd": worker_result.cost_usd}`) on success, or `worker.failed` (with `stage="worker"`, `duration_seconds=worker_result.duration_seconds`, `success=False`, `metadata={"error": worker_result.error}`) on failure.
- [ ] 3.4 In `_run_pipeline_inner`, before calling `run_eval`: emit `eval.started` with `stage="eval"`. Use the eval command count from whatever is being passed to `run_eval` (currently `BOOTSTRAP_EVAL_COMMANDS` via default, will change when `repo-profiling` lands).
- [ ] 3.5 In `_run_pipeline_inner`, after `run_eval` returns: emit `eval.completed` with `stage="eval"`, `success=eval_result.success`, and `metadata={"commands_passed": eval_result.commands_passed, "commands_run": eval_result.commands_run}`.
- [ ] 3.6 In `_run_pipeline_inner`, when scheduling a retry (both worker failure and eval failure paths): emit `retry.scheduled` with `metadata={"attempt": attempt, "reason": "worker_failed" or "eval_failed", "max_retries": max_retries}`.
- [ ] 3.7 In `_run_pipeline_inner`, after `create_pr` returns: emit `pr.created` (with `stage="pr"`, `metadata={"pr_url": pr_result.pr_url, "branch": pr_result.branch}`) on success, or `pr.failed` (with `stage="pr"`, `metadata={"error": pr_result.error}`) on failure.
- [ ] 3.8 In `_run_pipeline_inner` or `_run_openspec_review`, after the review stage completes: emit `openspec_review.completed` with `stage="openspec-review"`, `success=review_result.success`, `duration_seconds=review_result.duration_seconds`, `metadata={"archived": review_result.archived, "findings": review_result.findings}`.

## 4. Eval Per-Command Events

- [ ] 4.1 In `src/action_harness/evaluator.py`, add an optional `logger: EventLogger | None = None` parameter to `run_eval` (import `EventLogger` with a `TYPE_CHECKING` guard to avoid circular imports at runtime, or import directly since `event_log.py` does not import from `evaluator.py`).
- [ ] 4.2 In `run_eval`, after each command succeeds (exit code 0): if `logger` is not None, call `logger.emit("eval.command.passed", stage="eval", command=cmd_str)`.
- [ ] 4.3 In `run_eval`, when a command fails (nonzero exit code): if `logger` is not None, call `logger.emit("eval.command.failed", stage="eval", command=cmd_str, exit_code=result.returncode)`.
- [ ] 4.4 In `_run_pipeline_inner`, pass the `logger` to `run_eval(worktree_path, verbose=verbose, logger=logger)`.

## 5. Tests

- [ ] 5.1 In `tests/test_event_log.py`, add an integration-style test: create a temporary directory, instantiate `EventLogger`, emit several events of different types, close the logger, read the file, and assert: (a) each line parses as valid JSON, (b) all events have `timestamp`, `event`, and `run_id`, (c) event types match what was emitted, (d) metadata fields are present.
- [ ] 5.2 In `tests/test_event_log.py`, test the non-fatal behavior: mock the file handle's `write` method to raise `OSError`, call `emit`, and assert it does not raise and logs a warning (capture stderr or mock `typer.echo`).
- [ ] 5.3 In `tests/test_integration.py`, add a test that verifies `RunManifest.event_log_path` is populated after a pipeline run and that the referenced file exists and contains valid JSON-lines.

## 6. Self-Validation

- [ ] 6.1 Run `uv run pytest -v` and verify all tests pass, including new tests in `test_event_log.py`.
- [ ] 6.2 Run `uv run ruff check .` and verify no lint errors.
- [ ] 6.3 Run `uv run ruff format --check .` and verify no formatting issues.
- [ ] 6.4 Run `uv run mypy src/` and verify no type errors.
- [ ] 6.5 Run `uv run pytest tests/test_event_log.py -v` specifically and verify all event log tests pass.
