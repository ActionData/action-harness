## 1. Design Rules in CLAUDE.md

- [ ] 1.1 Add "Agent-debuggability" section to CLAUDE.md under "Key design rules" with three rules: (1) every function that performs I/O logs to stderr and returns a structured result — no fire-and-forget, (2) pipeline stages are independently callable with explicit typed parameters, (3) stderr is the diagnostic channel (progress, timing, outcomes), stdout is reserved for final output
- [ ] 1.2 Add "Logging conventions" subsection: use `typer.echo(..., err=True)` for stderr output, one line at stage entry (stage name + key inputs), one line at stage exit (stage name + outcome). Default is concise, `--verbose` adds subprocess detail.

## 2. Result Models

- [ ] 2.1 In `models.py`: define a `StageResult` dataclass with fields: `success` (bool), `stage` (str), `error` (str | None), `duration_seconds` (float | None). This is the base return type for all pipeline stages.
- [ ] 2.2 In `models.py`: define `WorktreeResult(StageResult)` adding `worktree_path` (Path | None), `branch` (str)
- [ ] 2.3 In `models.py`: define `WorkerResult(StageResult)` adding `commits_ahead` (int), `cost_usd` (float | None), `worker_output` (str | None)
- [ ] 2.4 In `models.py`: define `EvalResult(StageResult)` adding `commands_run` (int), `commands_passed` (int), `failed_command` (str | None), `feedback_prompt` (str | None)
- [ ] 2.5 In `models.py`: define `PrResult(StageResult)` adding `pr_url` (str | None), `branch` (str)
- [ ] 2.6 Tests in `tests/test_models.py`: construct each result type, verify field access, verify inheritance from StageResult

## 3. CLI Flags

- [ ] 3.1 In `cli.py`: add `--verbose` flag (bool, default False). Store in a module-level or context variable accessible to pipeline functions for controlling stderr detail level.
- [ ] 3.2 In `cli.py`: add `--dry-run` flag (bool, default False). When set, validate inputs, print planned execution sequence (worktree path, worker command outline, eval commands, PR title format), and exit with code 0.
- [ ] 3.3 Tests in `tests/test_cli.py`: add CliRunner tests for `--dry-run` (prints plan, exits 0), `--dry-run` with invalid inputs (exits 1), `--verbose` flag is accepted. Update `--help` test to verify new flags appear.

## 4. Validation

Run these commands to verify:

```bash
uv run pytest -v                  # all tests pass
uv run ruff check .               # no lint errors
uv run ruff format --check .      # formatting correct
uv run mypy src/                  # type checking passes
```

Verify manually:
1. `action-harness run --help` shows `--verbose` and `--dry-run` flags
2. `action-harness run --dry-run --change reframe-pipeline --repo .` prints planned stages and exits 0
3. `action-harness run --dry-run --change nonexistent --repo .` exits 1 with validation error
