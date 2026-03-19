## 1. PreflightResult Model

- [x] 1.1 Add `PreflightResult(StageResult)` to `models.py` with fields: `stage: Literal["preflight"] = "preflight"`, `checks: dict[str, bool]` (check name -> pass/fail), `failed_checks: list[str]` (names of failed checks for error messaging). Add `PreflightResult` to `StageResultUnion`.

## 2. Preflight Module

- [x] 2.1 Create `src/action_harness/preflight.py` with a `run_preflight()` function that accepts `worktree_path: Path`, `eval_commands: list[str]`, `change_name: str | None` (None for prompt mode), `repo_path: Path`, and `verbose: bool`. Returns `PreflightResult`. The function runs four checks in order: `check_worktree_clean`, `check_git_remote`, `check_eval_tools`, and `check_prerequisites` (only when `change_name` is not None). Each check logs entry/exit to stderr. Overall success requires all checks to pass.
- [x] 2.2 Implement `check_worktree_clean(worktree_path) -> bool`: runs `git status --porcelain` in the worktree. Returns True if output is empty (clean). Logs warning with dirty file list on failure.
- [x] 2.3 Implement `check_git_remote(worktree_path, verbose) -> bool`: runs `git ls-remote --exit-code origin HEAD` with timeout=30. Returns True on exit code 0. Catches `TimeoutExpired`, `FileNotFoundError`, `OSError`. Logs the actual error on failure.
- [x] 2.4 Implement `check_eval_tools(eval_commands) -> tuple[bool, list[str]]`: extracts the first token (tool binary) from each eval command via `shlex.split`, deduplicates, and checks each with `shutil.which()`. Returns (all_found, missing_tools). Logs which tools are missing.
- [x] 2.5 Implement `check_prerequisites(change_name, repo_path) -> bool`: imports and calls `read_prerequisites()` and `is_prerequisite_satisfied()` from `prerequisites.py`. Returns True if all prerequisites are satisfied or if no prerequisites exist. Logs unmet prerequisites.

## 3. Pipeline Integration

- [x] 3.1 Import `run_preflight` in `pipeline.py` and insert a preflight block in `_run_pipeline_inner` between worktree creation/restore and baseline eval. Guard with `skip_preflight` parameter. On failure, emit `preflight.failed` event, log the failed checks, and return early with `PrResult(success=False, stage="pipeline", error=...)`. On success, emit `preflight.passed` event. Append `PreflightResult` to `stages` list.
- [x] 3.2 Add `skip_preflight: bool = False` parameter to `_run_pipeline_inner` and `run_pipeline`. Thread it through from `run_pipeline` to `_run_pipeline_inner`.

## 4. CLI Flag

- [x] 4.1 Add `--skip-preflight` flag to the `run` command in `cli.py`. Pass it through to `run_pipeline()`. Update the help text to describe what preflight checks do.

## 5. Tests

- [ ] 5.1 Create `tests/test_preflight.py` with unit tests: (a) `check_worktree_clean` returns True on clean worktree, False on dirty; (b) `check_git_remote` returns True on reachable remote, False on unreachable; (c) `check_eval_tools` returns True when all tools found, False with correct missing list when tool absent; (d) `check_prerequisites` returns True when satisfied or no prereqs, False when unmet; (e) `run_preflight` returns success=True when all pass, success=False with correct failed_checks when any fail.
- [ ] 5.2 Add a pipeline integration test verifying that preflight failure short-circuits before worker dispatch (worker should not be called).

## 6. Validation

- [ ] 6.1 Run full validation suite: `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/` — all must pass with no regressions.
