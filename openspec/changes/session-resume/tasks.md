## 1. Model Changes [no dependencies]

- [ ] 1.1 Add `session_id: str | None = None` and `context_usage_pct: float | None = None` fields to `WorkerResult` in `models.py:32`
- [ ] 1.2 Add tests: (a) construct `WorkerResult(success=True, stage="worker", session_id="sess_abc123", context_usage_pct=0.45)`, roundtrip via `model_dump_json()` then `model_validate_json()`, assert `result.session_id == "sess_abc123"` and `result.context_usage_pct == pytest.approx(0.45)`. (b) Construct a `RunManifest` with a `WorkerResult` containing `session_id` and `context_usage_pct` in its `stages` list, roundtrip via `model_dump_json()` then `model_validate_json()`, assert the values survive the discriminated union serialization.

## 2. Worker Dispatch — Capture and Resume [depends: 1]

- [ ] 2.1 In `dispatch_worker()` in `worker.py`, capture `session_id` from JSON output: `session_id = output_data.get("session_id")`. Store it on the returned `WorkerResult` in both success and failure paths. Compute `context_usage_pct` from the JSON output using: `model_info = next(iter(output_data.get("modelUsage", {}).values()), {})`, `context_window = model_info.get("contextWindow", 1_000_000)`, `context_usage_pct = (usage.get("input_tokens", 0) + usage.get("output_tokens", 0)) / context_window` where `usage = output_data.get("usage", {})`.
- [ ] 2.2 Add `session_id: str | None = None` parameter to `dispatch_worker()`. When `session_id` is provided: (a) if `feedback` is None, raise `ValueError("resume requires feedback")`, (b) add `"--resume", session_id` to the CLI command, (c) omit `--system-prompt` from the command, (d) set `user_prompt = feedback` (not the opsx:apply instruction at `worker.py:73`). When `session_id` is None, keep current behavior unchanged.
- [ ] 2.3 Add tests with mock CLI JSON output `{"session_id": "sess_xyz", "cost_usd": 0.1, "result": "ok", "usage": {"input_tokens": 50000, "output_tokens": 20000}, "modelUsage": {"claude-opus-4-6[1m]": {"contextWindow": 1000000, "inputTokens": 50000, "outputTokens": 20000, "costUSD": 0.1}}}`: assert `result.session_id == "sess_xyz"`, assert `result.context_usage_pct == pytest.approx(0.07)`. Test dispatch without `session_id` — assert CLI command includes `--system-prompt` and does not include `--resume`. Test dispatch with `session_id="sess_abc"` — assert CLI command includes `--resume sess_abc` and does not include `--system-prompt`. Test dispatch with `session_id="sess_abc"` and `feedback=None` — assert `ValueError` is raised.

## 3. Pipeline — Eval Retry with Resume [depends: 2]

- [ ] 3.1 In `_run_pipeline_inner()`, inside the `while attempt <= max_retries:` loop, after eval failure: check `worker_result.context_usage_pct`. If below 0.6 and `worker_result.session_id is not None`, pass `session_id=worker_result.session_id` to the next `dispatch_worker()` call. Otherwise, pass `session_id=None` (fresh dispatch).
- [ ] 3.2 Handle resume fallback within the same loop iteration: after calling `dispatch_worker` with `session_id`, if `worker_result.success is False` and `session_id was not None`, log "session resume failed, retrying with fresh dispatch", set `session_id = None`, and call `dispatch_worker` again within the same iteration (do not increment `attempt`). Only increment `attempt` after the second (fresh) dispatch also fails.
- [ ] 3.3 Add tests: patch `dispatch_worker` and `run_eval`. Test 1: context usage 0.05, session_id present — verify `dispatch_worker` called with `session_id` on retry. Test 2: context usage 0.75 — verify `dispatch_worker` called with `session_id=None`. Test 3: resumed dispatch fails (returns `success=False`), verify fallback fresh dispatch is called without incrementing attempt count (total dispatch count = 3: initial + failed resume + fresh fallback, but attempt count = 1). Test 4: chained resumes — dispatch 1 returns `session_id="sess_a"`, retry 1 resumes with `sess_a` and returns `session_id="sess_b"`, retry 2 resumes with `sess_b` (not `sess_a`).

## 4. Pipeline — Review Fix-Retry with Resume [depends: 2]

- [ ] 4.1 In `_run_review_fix_retry()` in `pipeline.py`, iterate `stages` in reverse order and find the first `WorkerResult` where `success is True`. Use its `session_id` for the fix-retry dispatch. If no successful `WorkerResult` found or `session_id` is None, fall back to fresh dispatch (current behavior).
- [ ] 4.2 Add tests: review fix-retry with successful `WorkerResult` having `session_id="sess_abc"` — verify `dispatch_worker` called with `session_id="sess_abc"`. Test without `session_id` — verify fresh dispatch. Test resume failure — verify fallback to fresh dispatch.

## 5. Logging [depends: 3, 4]

- [ ] 5.1 Log resume decisions to stderr via `typer.echo(..., err=True)`: "resuming session {session_id} (context {pct}%)" on resume, "context usage {pct}% exceeds threshold, using fresh dispatch" on threshold exceeded, "session resume failed, retrying with fresh dispatch" on resume failure
- [ ] 5.2 Add resume-related fields to event logger `worker.dispatched` events: `session_id`, `context_usage_pct`, `resumed: bool`

## 6. Validation [depends: all]

- [ ] 6.1 Run full test suite (`uv run pytest -v`) and verify no regressions
- [ ] 6.2 Run lint and type checks (`uv run ruff check .` and `uv run mypy src/`)
- [ ] 6.3 Run tests with `-k session` to verify all session-resume tests pass in isolation
