## 1. Add RunStats model and compute_run_stats function

- [x] 1.1 Add `RunStats` Pydantic model to `src/action_harness/models.py` with fields: `passed: int`, `failed: int`, `total: int`, `success_rate: float`
- [x] 1.2 Add `compute_run_stats(manifests: list[RunManifest]) -> RunStats` function to `src/action_harness/reporting.py` that counts successes/failures and computes success rate
- [x] 1.3 Add unit tests for `compute_run_stats` covering mixed manifests and empty list cases

## 2. Refactor callers to use shared function

- [x] 2.1 Refactor `aggregate_report` in `reporting.py` to call `compute_run_stats` instead of inline success/failure counting
- [x] 2.2 Refactor `_gather_recent_runs` in `lead.py` to call `compute_run_stats` instead of inline success counting
- [x] 2.3 Update existing tests if needed to reflect refactored internals

## 3. Validation

- [x] 3.1 Run full validation suite (pytest, ruff, mypy) and fix any issues
