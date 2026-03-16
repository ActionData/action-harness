## ADDED Requirements

### Requirement: Checkpoint written after each pipeline stage
The pipeline SHALL write a checkpoint file after each major stage completes. The checkpoint captures enough state to resume from that point.

#### Scenario: Checkpoint after worktree creation
- **WHEN** the worktree stage completes successfully
- **THEN** a checkpoint file SHALL exist at `.action-harness/checkpoints/<run-id>.json` with `completed_stages` containing `"worktree"` and `worktree_path` set

#### Scenario: Checkpoint after PR creation
- **WHEN** the PR stage completes successfully
- **THEN** the checkpoint SHALL contain `pr_url` and `completed_stages` containing `"pr"`

#### Scenario: Checkpoint updated atomically
- **WHEN** the checkpoint is written
- **THEN** it SHALL be written via temp file + `os.replace()` to prevent corruption on crash

### Requirement: --resume flag resumes from checkpoint
The `harness run` command SHALL accept `--resume` with value `latest` or a specific run ID. When provided, the pipeline skips completed stages and resumes from the checkpoint's `current_stage`.

#### Scenario: Resume from latest checkpoint
- **WHEN** the user runs `harness run --change X --repo . --resume latest` and a checkpoint exists for change X
- **THEN** the pipeline SHALL skip all stages in `completed_stages` and resume from `current_stage`

#### Scenario: Resume with specific run ID
- **WHEN** the user runs `harness run --change X --repo . --resume <run-id>` and the checkpoint exists
- **THEN** the pipeline SHALL resume from that specific checkpoint

#### Scenario: No checkpoint exists
- **WHEN** `--resume` is provided but no checkpoint exists for the change
- **THEN** the pipeline SHALL log a warning and start fresh (no error)

#### Scenario: Worktree missing on resume
- **WHEN** resuming from a checkpoint but the worktree path no longer exists
- **THEN** the pipeline SHALL log a warning and start fresh from the worktree stage

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
- **WHEN** a `PipelineCheckpoint` is serialized via `model_dump_json()` and deserialized via `model_validate_json()`
- **THEN** all fields SHALL survive the roundtrip including nested `StageResultUnion` entries

### Requirement: Checkpoint compatible with existing features
The checkpoint SHALL store `session_id` for session-resume and the accumulated `stages` list for the manifest builder.

#### Scenario: Resumed run uses session_id from checkpoint
- **WHEN** resuming a run that had a successful worker dispatch with `session_id`
- **THEN** the retry loop SHALL use that `session_id` for `--resume` dispatch

#### Scenario: Resumed run produces complete manifest
- **WHEN** a run completes after resume
- **THEN** the manifest SHALL contain stage results from BOTH the checkpointed stages and the newly-run stages
