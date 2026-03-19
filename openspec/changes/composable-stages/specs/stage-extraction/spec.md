## ADDED Requirements

### Requirement: WorktreeStage extracts worktree creation logic
The `WorktreeStage` SHALL encapsulate worktree creation, workspace directory resolution, and checkpoint worktree restoration.

#### Scenario: Fresh worktree creation
- **WHEN** WorktreeStage runs without a checkpoint
- **THEN** it creates a git worktree via `create_worktree()`, sets `context.worktree_path` and `context.branch`, and returns a `WorktreeResult`

#### Scenario: Checkpoint worktree restoration
- **WHEN** WorktreeStage runs with a checkpoint that has a worktree_path
- **THEN** it restores the worktree path and branch from the checkpoint without creating a new worktree

### Requirement: WorkerEvalLoopStage extracts the dispatch-eval-retry loop
The `WorkerEvalLoopStage` SHALL encapsulate worker dispatch, eval execution, baseline eval, retry logic, session resume decisions, and progress file management as a single composite stage.

#### Scenario: Successful first attempt
- **WHEN** the worker produces commits and eval passes on the first attempt
- **THEN** it appends `WorkerResult` and `EvalResult` to `context.stages` and returns success

#### Scenario: Eval failure triggers retry
- **WHEN** eval fails and retries remain
- **THEN** it writes a progress file, formats eval feedback, and dispatches the worker again

#### Scenario: Session resume when context is fresh
- **WHEN** a retry is needed and prior context usage is below 60%
- **THEN** the worker is dispatched with `--resume <session_id>` instead of a fresh invocation

#### Scenario: Max retries exhausted
- **WHEN** eval fails and no retries remain
- **THEN** it returns a failed result with the last eval feedback

### Requirement: CreatePrStage extracts PR creation logic
The `CreatePrStage` SHALL encapsulate git push, `gh pr create`, rollback tag creation, and issue linking.

#### Scenario: PR created successfully
- **WHEN** CreatePrStage runs after successful worker-eval
- **THEN** it pushes the branch, creates the PR, tags the rollback point, sets `context.pr_url`, and returns a `PrResult`

#### Scenario: No commits to push
- **WHEN** CreatePrStage runs but the worker produced 0 commits
- **THEN** it returns a failed `PrResult` with an appropriate error

### Requirement: ProtectedPathsStage extracts protected paths checking
The `ProtectedPathsStage` SHALL check changed files against protected patterns and flag the PR if matches are found.

#### Scenario: Protected files detected
- **WHEN** changed files match patterns in `.harness/protected-paths.yml`
- **THEN** it comments on the PR, adds the "protected-paths" label, and populates `context.protected_files`

#### Scenario: No protected paths config
- **WHEN** `.harness/protected-paths.yml` does not exist
- **THEN** the stage succeeds with no findings

### Requirement: ReviewAgentsStage extracts review dispatch and fix-retry
The `ReviewAgentsStage` SHALL encapsulate parallel review agent dispatch, tolerance-based triage, fix-retry loops, and PR comment posting.

#### Scenario: Clean review
- **WHEN** review agents find no actionable findings
- **THEN** it posts a clean review comment and returns success

#### Scenario: Findings trigger fix-retry
- **WHEN** review agents find actionable findings
- **THEN** it dispatches a worker with review feedback, re-runs eval, pushes fixes, and runs a verification review

### Requirement: OpenSpecReviewStage extracts OpenSpec review logic
The `OpenSpecReviewStage` SHALL encapsulate spec validation, semantic review, and archival. It is skipped when running in prompt mode.

#### Scenario: Prompt mode skips openspec review
- **WHEN** `context.prompt` is set (freeform task, no OpenSpec change)
- **THEN** the stage returns success immediately without dispatching a review

#### Scenario: OpenSpec review with archival
- **WHEN** all tasks are complete and review passes
- **THEN** it archives the change and returns `archived=True`

### Requirement: MergeGateStage extracts auto-merge logic
The `MergeGateStage` SHALL encapsulate merge gate checks (protected files, review status, openspec review, CI) and conditional merge execution.

#### Scenario: All gates pass
- **WHEN** auto_merge is enabled and all gates pass
- **THEN** it merges the PR and returns `merged=True`

#### Scenario: Gate blocked
- **WHEN** any gate fails
- **THEN** it posts a comment with gate status and returns `merged=False`

#### Scenario: Auto-merge disabled
- **WHEN** `context.auto_merge` is False
- **THEN** the stage is skipped entirely

### Requirement: Pipeline runner iterates over stage list
The refactored `_run_pipeline_inner` SHALL accept a list of `Stage` objects and iterate over them, passing `FlowContext` to each. It replaces the inlined stage logic with stage dispatch.

#### Scenario: Sequential execution
- **WHEN** the runner receives a list of stages
- **THEN** it executes them in order, passing the shared FlowContext

#### Scenario: Stage failure stops pipeline
- **WHEN** a stage returns `success=False`
- **THEN** the runner stops execution and returns the failure result

#### Scenario: Checkpoint written after each stage
- **WHEN** a stage completes successfully
- **THEN** a checkpoint is written with that stage's name as `completed_stage`
