## 1. Baseline Eval

- [ ] 1.1 In `evaluator.py`: add `run_baseline_eval(worktree_path, eval_commands, verbose) -> dict[str, bool]` that runs each eval command and records pass (True) / fail (False) per command. Does NOT stop on first failure — runs all commands. Returns a dict mapping command string to pass/fail.
- [ ] 1.2 In `models.py:RunManifest`: add `baseline_eval: dict[str, bool] = {}` field.

## 2. Regression-Aware Eval

- [ ] 2.1 In `evaluator.py:run_eval`: add optional `baseline: dict[str, bool] | None = None` parameter. When provided, after a command fails, check `baseline.get(cmd_str)`. If baseline shows the command was already failing (`False`), log "pre-existing failure" to stderr and continue (don't count as regression). Only return failure for commands that were passing in baseline but now fail.
- [ ] 2.2 In `evaluator.py:EvalResult`: add `pre_existing_failures: list[str] = []` field for commands that were already failing.

## 3. Pipeline Integration

- [ ] 3.1 In `pipeline.py:_run_pipeline_inner`: after worktree creation and before the worker dispatch loop, call `run_baseline_eval(worktree_path, eval_commands, verbose)`. Store the result.
- [ ] 3.2 In `pipeline.py`: pass `baseline=baseline` to all `run_eval` calls (main loop and fix-retry).
- [ ] 3.3 In `pipeline.py:_build_manifest`: add `baseline_eval` parameter and set on manifest.

## 4. Tests

- [ ] 4.1 In `tests/test_evaluator.py`: test `run_baseline_eval` — runs all commands, returns dict, doesn't stop on first failure.
- [ ] 4.2 In `tests/test_evaluator.py`: test `run_eval` with baseline — pre-existing failure (was failing, still failing) doesn't cause eval failure. Regression (was passing, now failing) does cause failure.
- [ ] 4.3 In `tests/test_integration.py`: test pipeline with baseline — pre-existing lint failure doesn't trigger retry.

## 5. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
