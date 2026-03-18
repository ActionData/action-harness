## ADDED Requirements

### Requirement: openspec-update-tasks hook syncs task completion
The `openspec-update-tasks` hook SHALL detect completed tasks by comparing the worktree's tasks.md against the source repo's tasks.md and syncing checkbox state. It fires on `after_attempt` (after worker completes, before eval).

Source path: `context.repo / "openspec" / "changes" / context.change_name / "tasks.md"`
Worktree path: `context.worktree_path / "openspec" / "changes" / context.change_name / "tasks.md"`

#### Scenario: Tasks checked off after worker attempt
- **WHEN** `after_attempt` fires and the worktree's tasks.md has `- [x]` on a line where the source has `- [ ]`
- **THEN** the hook updates that line in the source repo's tasks.md from `- [ ]` to `- [x]`
- **THEN** other lines in the source tasks.md are NOT modified

#### Scenario: One-way promotion only
- **WHEN** `after_attempt` fires and the worktree's tasks.md has `- [ ]` on a line where the source has `- [x]` (a later retry reverted a previously completed task)
- **THEN** the hook does NOT demote the source line — it stays `- [x]`

#### Scenario: No task changes
- **WHEN** `after_attempt` fires and no lines differ in checkbox state
- **THEN** the hook does nothing and returns silently

#### Scenario: tasks.md does not exist in worktree
- **WHEN** `after_attempt` fires but the worktree tasks.md path does not exist (prompt mode or non-OpenSpec flow)
- **THEN** the hook does nothing and returns silently

#### Scenario: Source tasks.md has new tasks added externally
- **WHEN** the source tasks.md has more lines than the worktree version (a task was added between attempts)
- **THEN** the hook only compares lines present in both files and does NOT overwrite or remove the new source lines

### Requirement: openspec-archive hook archives completed changes
The `openspec-archive` hook SHALL archive the OpenSpec change when all tasks are complete, using existing archival logic from `openspec_reviewer.py`. It fires on `on_success`.

#### Scenario: All tasks complete on success
- **WHEN** `on_success` fires and all tasks in the source tasks.md are checked off (`- [x]`)
- **THEN** the hook archives the change (moves to `openspec/archive/`)

#### Scenario: Partial completion on success
- **WHEN** `on_success` fires but some tasks in the source tasks.md remain unchecked
- **THEN** the hook does not archive and logs the count of remaining unchecked tasks to stderr

#### Scenario: No OpenSpec change (prompt mode)
- **WHEN** `on_success` fires but `context.prompt` is set (no OpenSpec change)
- **THEN** the hook does nothing and returns silently

#### Scenario: OpenSpecReviewStage detects prior archival
- **WHEN** the `openspec-archive` hook has already archived the change
- **THEN** `OpenSpecReviewStage` detects the change directory no longer exists, logs "already archived by hook", and skips its own archival step (validation and semantic review still run against the archived copy)
