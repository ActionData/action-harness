## Why

Test fixtures create real git worktrees in `/tmp/action-harness-*/` via `create_worktree`. These are never cleaned up, accumulating ~600 temp directories over repeated test runs. Each contains a full worktree checkout.

Additionally, successful pipeline runs leave worktrees in `/tmp` forever — cleanup only happens on failure.

## What Changes

- Test fixtures that create worktrees should clean them up in teardown
- Successful pipeline runs should clean up the worktree after PR creation (the branch is pushed, worktree is no longer needed)

## Capabilities

### New Capabilities

- `test-cleanup`: Test fixtures clean up worktrees and temp dirs. Successful pipelines clean up worktrees after pushing.

### Modified Capabilities

## Impact

- `tests/test_worktree.py` — fixture teardown calls `cleanup_worktree`
- `tests/test_integration.py` — fixture teardown cleans worktrees
- `src/action_harness/pipeline.py` — cleanup worktree on success path
