Prerequisites: implement `clean-eval-environment` first so VIRTUAL_ENV stripping applies to both baseline and post-worker eval.

## 1. Baseline Eval

- [x] 1.1 In `evaluator.py`: add `run_baseline_eval(worktree_path, eval_commands, verbose) -> dict[str, bool]` that runs EACH eval command (does NOT stop on first failure — runs all commands) and records pass (True) / fail (False) per command. Use the same `clean_env` pattern from `run_eval` to strip VIRTUAL_ENV. Return a dict mapping command string to pass/fail. Log each result to stderr.
- [x] 1.2 In `models.py:RunManifest`: add `baseline_eval: dict[str, bool] = {}` field.
- [x] 1.3 In `models.py:EvalResult`: add `pre_existing_failures: list[str] = []` field.

## 2. Regression-Aware Eval

- [x] 2.1 In `evaluator.py:run_eval`: add optional `baseline: dict[str, bool] | None = None` parameter. Change the control flow: when `baseline` is provided and a command fails, check `baseline.get(cmd_str)`. If baseline shows the command was already failing (`False`), log "pre-existing failure (was already failing at baseline)" to stderr, add to `pre_existing_failures` list, and CONTINUE to the next command (do not return early). Only return `success=False` for regressions (commands that were passing at baseline but now fail). Set `failed_command` to the first regression command. Set `feedback_prompt` to formatted feedback for regression(s) only, not pre-existing failures.

## 3. Pipeline Integration

- [ ] 3.1 In `pipeline.py:_run_pipeline_inner`: after worktree creation (after the assert block, before `attempt = 0`), call `baseline = run_baseline_eval(worktree_path, eval_commands, verbose)`. Emit `baseline_eval.started` and `baseline_eval.completed` events via `logger.emit()` with command count, pass count, and fail count.
- [ ] 3.2 Pass `baseline=baseline` to `run_eval` in the main eval loop (~line 349) and in `_run_review_fix_retry` (~line 656). Add a `baseline: dict[str, bool] | None = None` parameter to `_run_review_fix_retry` and thread from `_run_pipeline_inner`.
- [ ] 3.3 In `pipeline.py:_build_manifest`: add `baseline_eval: dict[str, bool] | None = None` parameter and set on manifest.

## 4. Tests

- [ ] 4.1 In `tests/test_evaluator.py`: test `run_baseline_eval` — runs ALL commands even when some fail. Returns dict with correct pass/fail per command.
- [ ] 4.2 In `tests/test_evaluator.py`: test `run_eval` with baseline — pre-existing failure (was failing, still failing) does NOT cause eval failure, added to `pre_existing_failures`. Regression (was passing, now failing) DOES cause failure with `failed_command` set. Worker fixed issue (was failing, now passing) noted as success.
- [ ] 4.3 In `tests/test_integration.py`: test pipeline with baseline — pre-existing lint failure doesn't trigger retry. Only regressions trigger retry.

## 5. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
