## Why

Pipeline runs can take 30-60+ minutes. When a run fails mid-pipeline (rate limit, crash, network error), all progress is lost — the harness restarts from scratch on the next `harness run`. We experienced this directly: the agent-definitions run died during review fix-retry and we had to re-implement the entire change from scratch.

Checkpoint-resume saves pipeline state after each completed stage. On failure, a subsequent `harness run` with `--resume` picks up from the last completed checkpoint instead of starting over.

Distinct from `retry-progress` (within-stage retry continuity) — this is about cross-stage resumption after process-level failures.

## What Changes

- Pipeline writes a checkpoint file after each major stage (worktree, worker, eval, PR, review)
- New `--resume` flag on `harness run` that reads the checkpoint and skips completed stages
- Checkpoint stored as JSON in `.action-harness/checkpoints/<run-id>.json`
- Checkpoint includes: current stage, worktree path, branch, PR URL, session IDs, stage results
- Stale checkpoints cleaned up on successful pipeline completion

## Capabilities

### New Capabilities
- `checkpoint-resume`: Write pipeline checkpoints after each stage, resume from the last checkpoint on subsequent runs with `--resume`.

### Modified Capabilities
None

## Impact

- `pipeline.py` — write checkpoint after each stage, read checkpoint on `--resume`
- `cli.py` — add `--resume` flag (accepts a run ID or "latest")
- `models.py` — new `PipelineCheckpoint` model
- `.action-harness/checkpoints/` — checkpoint JSON files
- No changes to worker, eval, review agents, or worktree modules
