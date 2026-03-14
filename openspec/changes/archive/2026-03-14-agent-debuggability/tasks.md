## 1. Design Rules in CLAUDE.md

- [ ] 1.1 Add "Agent-debuggability" section to CLAUDE.md under "Key design rules" with three rules: (1) every function that performs I/O logs to stderr and returns a structured result — no fire-and-forget, (2) pipeline stages are independently callable with explicit typed parameters, (3) stderr is the diagnostic channel (progress, timing, outcomes), stdout is reserved for final output (exception: `--dry-run` prints the plan to stdout because the plan is the final output)
- [ ] 1.2 Add "Logging conventions" subsection: use `typer.echo(..., err=True)` for stderr output, one line at stage entry (stage name + key inputs), one line at stage exit (stage name + outcome). Default is concise, `--verbose` adds subprocess detail. Migrate existing `typer.echo` calls in `cli.py` (lines 82-83) to use `err=True` to conform.

## 2. Result Models

- [ ] 2.1 In `models.py`: define a `StageResult` Pydantic model with fields: `success` (bool), `stage` (str), `error` (str | None = None), `duration_seconds` (float | None = None). This is the base return type for all pipeline stages.
- [ ] 2.2 In `models.py`: define `WorktreeResult(StageResult)` adding `worktree_path` (Path | None = None), `branch` (str)
- [ ] 2.3 In `models.py`: define `WorkerResult(StageResult)` adding `commits_ahead` (int = 0), `cost_usd` (float | None = None), `worker_output` (str | None = None)
- [ ] 2.4 In `models.py`: define `EvalResult(StageResult)` adding `commands_run` (int = 0), `commands_passed` (int = 0), `failed_command` (str | None = None), `feedback_prompt` (str | None = None)
- [ ] 2.5 In `models.py`: define `PrResult(StageResult)` adding `pr_url` (str | None = None), `branch` (str)
- [ ] 2.6 Tests in `tests/test_models.py`: construct each result type for both success and failure cases. Verify field access, verify inheritance from StageResult. For failure results, verify `success=False` and `error` contains the failure message. For success results, verify `error is None`.

## 3. CLI Flags

- [ ] 3.1 In `cli.py`: add `--verbose` flag (bool, default False). Pass `verbose` as an explicit parameter to each pipeline stage function — do not use module-level state or context variables (this would violate stage isolation).
- [ ] 3.2 In `cli.py`: add `--dry-run` flag (bool, default False). When set, validate inputs, print planned execution sequence to stdout (worktree path, worker command outline, eval commands, PR title format), and exit with code 0. When both `--verbose` and `--dry-run` are passed, behavior is identical to `--dry-run` alone (verbose has no effect because no subprocesses are executed).
- [ ] 3.3 Tests in `tests/test_cli.py`: add CliRunner tests for: (a) `--dry-run` prints plan containing the change name, worktree path, and eval commands, exits 0; (b) `--dry-run` with invalid inputs exits 1; (c) `--verbose` flag is accepted; (d) `--help` shows `--verbose` and `--dry-run` flags.

## 4. Validation

Run these commands to verify:

```bash
uv run pytest -v                  # all tests pass
uv run ruff check .               # no lint errors
uv run ruff format --check .      # formatting correct
uv run mypy src/                  # type checking passes
```
