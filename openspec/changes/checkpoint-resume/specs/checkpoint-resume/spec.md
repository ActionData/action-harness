## ADDED Requirements

### Requirement: Checkpoint written after each macro-stage
The pipeline SHALL write a checkpoint file after each macro-stage completes. Macro-stages are: worktree, worker_eval (entire retry loop), pr, review (entire review cycle), openspec_review.

#### Scenario: Checkpoint after worktree creation
- **WHEN** the worktree stage completes successfully
- **THEN** a checkpoint file SHALL exist at `.action-harness/checkpoints/<run-id>.json` with `completed_stage` set to `"worktree"` and `worktree_path` set

#### Scenario: Checkpoint after worker+eval loop
- **WHEN** the worker+eval retry loop completes with eval passing
- **THEN** the checkpoint SHALL have `completed_stage = "worker_eval"`, `last_worker_result` set, and `last_eval_result` set

#### Scenario: Checkpoint after PR creation
- **WHEN** the PR stage completes successfully
- **THEN** the checkpoint SHALL contain `pr_url` and `completed_stage = "pr"`

#### Scenario: Checkpoint written atomically
- **WHEN** the checkpoint is written
- **THEN** it SHALL be written via temp file + `os.replace()` to prevent corruption on crash

### Requirement: --resume flag resumes from checkpoint
The `harness run` command SHALL accept `--resume` with value `latest` or a specific run ID. When provided, the pipeline skips completed macro-stages and resumes from the next stage after `completed_stage`.

#### Scenario: Resume after PR creation
- **WHEN** resuming from a checkpoint with `completed_stage = "pr"` and a valid worktree
- **THEN** the pipeline SHALL skip worktree creation, worker+eval, and PR creation. It SHALL restore `worktree_path`, `branch`, `worker_result`, `eval_result`, `pr_url`, and `stages` from the checkpoint. It SHALL start at the review stage.

#### Scenario: Resume after worker_eval
- **WHEN** resuming from a checkpoint with `completed_stage = "worker_eval"`
- **THEN** `create_pr` SHALL receive the `worker_result` and `eval_result` from the checkpoint

#### Scenario: No checkpoint exists
- **WHEN** `--resume` is provided but no checkpoint exists for the change
- **THEN** the pipeline SHALL log a warning and start fresh (no error)

#### Scenario: Worktree missing on resume
- **WHEN** resuming from a checkpoint but the worktree path no longer exists
- **THEN** the pipeline SHALL log a warning and start fresh from the worktree stage

#### Scenario: Branch HEAD changed since checkpoint
- **WHEN** resuming from a checkpoint but the branch HEAD SHA differs from `branch_head_sha`
- **THEN** the pipeline SHALL log a warning and start fresh

#### Scenario: Crash mid-retry-loop resumes at worker_eval
- **WHEN** the pipeline crashes during worker attempt 2 of the retry loop (before eval passes)
- **THEN** the checkpoint `completed_stage` SHALL be `"worktree"` (the last fully-completed macro-stage). Resume re-runs the entire worker+eval loop.

### Requirement: CLI flags captured in checkpoint
The checkpoint SHALL store `auto_merge`, `skip_review`, and `review_cycle` values. On resume, the checkpoint's values are used, not CLI arguments.

#### Scenario: Resume uses checkpoint's auto_merge flag
- **WHEN** the original run used `--auto-merge` and the resume run omits it
- **THEN** the pipeline SHALL use `auto_merge=True` from the checkpoint

### Requirement: Checkpoint cleaned up on success
On successful pipeline completion, the checkpoint file SHALL be deleted.

#### Scenario: Successful run cleans checkpoint
- **WHEN** the pipeline completes successfully and a checkpoint file exists
- **THEN** the checkpoint file SHALL be deleted

#### Scenario: Failed run preserves checkpoint
- **WHEN** the pipeline fails
- **THEN** the checkpoint file SHALL remain for future resume

### Requirement: PipelineCheckpoint model
The checkpoint SHALL be stored as a `PipelineCheckpoint` Pydantic model serialized to JSON.

#### Scenario: Checkpoint roundtrip
- **WHEN** a `PipelineCheckpoint` with `session_id="sess-123"`, `stages` containing a `WorktreeResult(worktree_path=Path("/tmp/wt"))` and a `WorkerResult(cost_usd=0.42)` is serialized via `model_dump_json()` and deserialized via `model_validate_json()`
- **THEN** `result.session_id` SHALL equal `"sess-123"`, `result.stages[0].worktree_path` SHALL equal `Path("/tmp/wt")`, and `result.stages[1].cost_usd` SHALL equal `0.42`

### Requirement: Resumed run produces complete manifest
When a run completes after resume, the manifest SHALL contain stage results from both checkpointed and newly-run stages.

#### Scenario: Manifest after resume
- **WHEN** a run resumes from `completed_stage = "pr"` and completes review + openspec-review
- **THEN** the manifest `stages` list SHALL contain the worktree, worker, eval, and PR results from the checkpoint PLUS the review and openspec-review results from the resumed run

### Requirement: find_latest_checkpoint matches by change name
The `find_latest_checkpoint` function SHALL find the most recent checkpoint for a given change name by reading each checkpoint file and comparing the `change_name` field.

#### Scenario: Multiple checkpoints for different changes
- **WHEN** checkpoints exist for changes `add-logging` and `fix-auth`
- **THEN** `find_latest_checkpoint(repo, "add-logging")` SHALL return only the `add-logging` checkpoint
