## 1. Progress File Writing [no dependencies]

- [x] 1.1 Create `src/action_harness/progress.py` with `write_progress(worktree_path: Path, attempt: int, worker_result: WorkerResult, eval_result: EvalResult) -> None`. Appends an `## Attempt {N}` section to `.harness-progress.md` in the worktree root. Each section contains: `- **Commits**: {worker_result.commits_ahead}`, `- **Eval result**: {"PASSED" if eval_result.success else "FAILED"}`, `- **Feedback**: {eval_result.feedback_prompt}` (if failed), `- **Duration**: {worker_result.duration_seconds}s`, `- **Cost**: ${worker_result.cost_usd}`. On first call, creates the file with a `# Harness Progress\n\n` header.
- [x] 1.2 Ensure `.harness-progress.md` is added to the worktree's `.gitignore` when first created. Only append if `.harness-progress.md` is not already present in `.gitignore` (idempotent). If `.gitignore` does not exist, create it with just this entry.
- [x] 1.3 Add tests: first call creates file with `## Attempt 1` header, assert file contains `str(worker_result.commits_ahead)`, `str(worker_result.cost_usd)`, `str(worker_result.duration_seconds)`, `eval_result.feedback_prompt` text, and `FAILED` when eval failed. Second call appends `## Attempt 2` without overwriting Attempt 1. Assert `.gitignore` contains `.harness-progress.md`. Assert PASSED written when eval succeeds.

## 2. Progress File Reading in Worker Prompt [depends: 1]

- [x] 2.1 In `dispatch_worker()` in `worker.py`, before building the CLI command: check if `.harness-progress.md` exists in `worktree_path`. If it does, read its contents. Prepend progress contents to the user prompt: `user_prompt = f"{progress_contents}\n\n{user_prompt}"`. The base task prompt (opsx:apply instruction or freeform prompt) and any feedback follow after the progress contents. Do NOT restructure the existing prompt — just prepend progress when available.
- [x] 2.2 Add tests: when `.harness-progress.md` exists in worktree, assert user prompt starts with the progress file contents. When file does not exist, assert user prompt is unchanged. Assert progress contents appear before the task prompt text.

## 3. Pre-work Eval on Retries [no dependencies]

- [x] 3.1 In `_run_pipeline_inner()`, inside the `while attempt <= max_retries:` loop, at the top of each retry iteration: run pre-work eval ONLY when the prior iteration produced commits (i.e., the prior `worker_result.commits_ahead > 0`). If the prior worker failed with zero commits, skip pre-work eval (the worktree is unchanged). When running pre-work eval: call `run_eval(worktree_path, eval_commands=eval_commands)` as a pre-work check. If this eval passes, log "pre-work eval passed, skipping retry", set `eval_result` to this pre-work eval result (so `create_pr` gets the correct result), and `break` out of the retry loop. The `worker_result` from the prior iteration is still valid for `create_pr`. If this eval fails, set `feedback = pre_work_eval_result.feedback_prompt` (replacing stale feedback) and continue to dispatch the retry worker.
- [x] 3.2 Log pre-work eval to the event logger: `eval.pre_work` event with `success`, `commands_passed`, `commands_run`.
- [x] 3.3 Add tests: patch `run_eval` and `dispatch_worker`. Test 1: pre-work eval returns `success=True` — assert `dispatch_worker` is NOT called for that retry, assert `create_pr` is called with the pre-work eval result and the prior worker result. Test 2: pre-work eval returns `success=False` with `feedback_prompt="mypy error"` — assert `dispatch_worker` IS called with `feedback="mypy error"` (not stale feedback). Test 3: prior worker produced zero commits (worker failure) — assert pre-work eval is NOT called, worker is dispatched directly with the worker error as feedback.

## 4. Integration — Write Progress in Pipeline [depends: 1, 3]

- [x] 4.1 In `_run_pipeline_inner()`, after each worker dispatch + eval cycle (and before the next retry): call `write_progress(worktree_path, attempt, worker_result, eval_result)`. Do NOT write progress on the first attempt if eval passes (no retry will follow). Write progress only when eval fails and a retry will follow.
- [x] 4.2 Review and update existing tests in `tests/test_integration.py` that mock the retry loop to account for the new pre-work eval call and progress file writing.
- [ ] 4.3 Add integration test: 2-retry scenario (mocked). Verify `.harness-progress.md` has 2 attempt sections after both retries. Verify the retry worker's prompt contains progress contents. Verify pre-work eval is called before the second retry dispatch.

## 5. Validation [depends: all]

- [ ] 5.1 Run full test suite (`uv run pytest -v`) and verify no regressions
- [ ] 5.2 Run lint and type checks (`uv run ruff check .` and `uv run mypy src/`)
- [ ] 5.3 Run a targeted test that exercises a 2-retry scenario end-to-end (mocked) and verify: `.harness-progress.md` has 2 attempt sections, retry worker prompt contains progress contents, pre-work eval is called before retry dispatch.
