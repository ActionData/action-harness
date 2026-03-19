## Context

The pipeline currently validates CLI inputs (repo exists, CLIs in PATH) at startup via `validate_inputs()` in `cli.py`, then creates a worktree, and immediately dispatches a Claude Code worker. There's no validation of the *worktree environment* itself — whether eval tools are actually runnable, whether git remotes are reachable for pushing, or whether OpenSpec prerequisites are satisfied. These failures surface mid-worker-session or post-eval, wasting tokens.

## Goals / Non-Goals

**Goals:**
- Run deterministic checks after worktree creation, before worker dispatch
- Detect missing eval tool binaries (e.g., `uv`, `pytest`, `npm`) in the worktree
- Verify git remote is reachable (worker needs to push commits)
- Check OpenSpec prerequisites are met (for change mode)
- Verify worktree is clean (no uncommitted changes from a prior failed run)
- Return structured `PreflightResult` with per-check pass/fail details
- Fail fast with actionable error messages
- Support `--skip-preflight` to bypass when checks are too conservative

**Non-Goals:**
- Runtime checks (API connectivity, token balance) — those are non-deterministic
- Eval command execution (that's the eval stage's job)
- Validating change artifact quality (that's the OpenSpec review stage)

## Decisions

### PreflightResult uses a checks dict, not individual fields

**Decision:** `PreflightResult` has a `checks: dict[str, bool]` field mapping check names to pass/fail, plus a `failed_checks: list[str]` for actionable messaging.

**Rationale:** Individual boolean fields per check would require model changes every time a check is added. A dict is extensible without schema changes. The `failed_checks` list provides the error message content directly.

### Preflight runs after worktree, before baseline eval

**Decision:** Insert preflight between worktree creation and baseline eval in `_run_pipeline_inner`.

**Rationale:** Preflight needs the worktree to exist (to check tool binaries, git state). It must run before baseline eval because if eval tools are missing, baseline eval will fail with confusing errors. Preflight catches this with a clear "uv not found" message instead of a cryptic eval failure.

### Eval tool detection uses shutil.which, not subprocess

**Decision:** Check eval tool availability via `shutil.which()` on the first token of each eval command, not by running the command.

**Rationale:** Running eval commands would duplicate the eval stage's purpose. `shutil.which()` is fast, deterministic, and sufficient to detect "tool not installed" — the most common class of eval failure.

### Git remote check uses `git ls-remote` with a short timeout

**Decision:** Verify remote reachability with `git ls-remote --exit-code origin HEAD` using a 30-second timeout.

**Rationale:** `git ls-remote` is a lightweight network probe that doesn't fetch data. A 30s timeout is generous enough for slow networks but short enough to fail fast on auth/DNS issues.

### Failed preflight is fatal (pipeline aborts)

**Decision:** A failed preflight returns early with a `PrResult(success=False)`, same as a failed worktree stage. No retries.

**Rationale:** Preflight failures are environment problems, not code problems. Retrying won't help — the tool binary won't magically appear. Failing fast preserves the "no wasted tokens" design goal.

## Risks / Trade-offs

**[Risk] Overly strict checks block valid dispatches** -> Mitigate with `--skip-preflight`. Also, each individual check is lenient: tool-not-found is fatal, but transient git remote flakes just warn.

**[Trade-off] git ls-remote adds ~1-5s of latency** -> Acceptable. Worker dispatch takes 20-40 minutes. A 5s preflight is negligible.

**[Trade-off] shutil.which may not match the worktree's PATH** -> We run `shutil.which` in the pipeline process, which has the same PATH as the worker subprocess. If `uv` is in PATH for the pipeline, it's in PATH for the worker.
