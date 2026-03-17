## Context

`create_worktree` uses `tempfile.mkdtemp` for non-managed worktrees. Tests call `create_worktree` with real git repos. Neither tests nor the success pipeline path clean up these directories.

## Goals / Non-Goals

**Goals:**
- Zero leaked temp dirs after a test run
- Successful pipeline runs clean up worktrees

**Non-Goals:**
- Cleaning up managed workspaces (that's `action-harness clean`)

## Decisions

### 1. Test fixtures use yield + cleanup

Convert test fixtures that create worktrees from plain functions to generators that yield the result, then clean up in the finally block.

### 2. Pipeline cleans worktree on success after all stages complete

After the openspec-review stage (the last stage), if the pipeline succeeded, call `cleanup_worktree` on the temp worktree. For managed workspaces, skip cleanup (they persist by design).
