# test-cleanup Specification

## Purpose
TBD - created by archiving change test-cleanup. Update Purpose after archive.
## Requirements
### Requirement: Test fixtures clean up worktrees
Test fixtures that create worktrees SHALL clean them up after the test completes, including the temp directory parent.

#### Scenario: Worktree cleaned after test
- **WHEN** a test using `create_worktree` completes (pass or fail)
- **THEN** the worktree directory and its parent temp dir no longer exist

### Requirement: Pipeline cleans worktree on success
When the pipeline completes successfully with a temp-dir worktree (not a managed workspace), the worktree SHALL be cleaned up after all stages complete.

#### Scenario: Temp worktree cleaned on success
- **WHEN** the pipeline succeeds and the worktree is a temp dir (not a managed workspace)
- **THEN** the worktree directory does not exist after `run_pipeline` returns

#### Scenario: Managed workspace preserved on success
- **WHEN** the pipeline succeeds and the worktree is a managed workspace under harness home
- **THEN** the worktree is NOT removed (cleaned via `action-harness clean`)

