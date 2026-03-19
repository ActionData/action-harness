## Why

When a Claude Code worker dispatch fails due to environment problems — missing eval tool binaries, unresolvable git remotes, unmet OpenSpec prerequisites — the harness wastes an entire worker session (tokens, time, context window) before discovering the failure. These failures are deterministic and detectable before dispatch. A preflight check between worktree creation and worker dispatch would catch them early and fail fast with actionable diagnostics.

## What Changes

- Add a new `preflight.py` module with deterministic pre-dispatch validation checks
- Add a `PreflightResult` model to the stage result union
- Insert preflight checks into `_run_pipeline_inner` between worktree creation and worker dispatch
- Emit structured events for preflight pass/fail
- Support `--skip-preflight` flag to bypass checks when needed

## Capabilities

### New Capabilities
- `dispatch-preflight`: Deterministic validation between worktree creation and worker dispatch that verifies the environment is ready for a Claude Code worker. Checks: git remote reachable, eval tool binaries exist, OpenSpec prerequisites met (for change mode), worktree working directory clean.

### Modified Capabilities
<!-- None — this inserts a new stage without changing existing stage behavior -->

## Impact

- **Code**: New `preflight.py` module (~150 lines). `models.py` gains `PreflightResult`. `pipeline.py` gains a preflight block between worktree and worker stages. `cli.py` gains `--skip-preflight` flag.
- **CLI**: New `--skip-preflight` flag on `harness run`. Default behavior runs preflight; flag skips it.
- **Tests**: New `test_preflight.py` with unit tests for each check. Pipeline integration tests updated.
- **Dependencies**: None.
- **Blocked by**: Nothing.
- **Blocks**: Nothing.
