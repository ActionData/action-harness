## Context

The pipeline flows through stages: worktree → worker → eval → retry loop → PR → protection → review loop → openspec-review. Each stage produces a result that feeds the next. A failure at any point loses all prior work.

The run manifest already captures all stage results at the END of the pipeline. Checkpoint-resume captures them DURING the pipeline, so a crashed run can be resumed.

## Goals / Non-Goals

**Goals:**
- Checkpoint file written after each major stage
- `--resume <run-id>` or `--resume latest` to pick up from last checkpoint
- Checkpoint includes enough state to skip completed stages
- Stale checkpoints cleaned up on successful completion
- Works with all existing features (session-resume, retry-progress, auto-merge)

**Non-Goals:**
- Resuming within a stage (e.g., mid-worker dispatch) — that's `session-resume` + `retry-progress`
- Distributed checkpoints (multiple machines) — local files only
- Checkpoint across different change names (each change has its own checkpoint)
- UI for browsing checkpoints

## Decisions

### 1. Checkpoint file structure

```python
class PipelineCheckpoint(BaseModel):
    run_id: str
    change_name: str
    repo_path: str
    completed_stages: list[str]  # ["worktree", "worker", "eval", "pr"]
    current_stage: str  # next stage to run
    worktree_path: str | None
    branch: str | None
    pr_url: str | None
    session_id: str | None  # for session-resume on retry
    last_worker_result: WorkerResult | None
    last_eval_result: EvalResult | None
    protected_files: list[str]
    stages: list[StageResultUnion]  # accumulated results
    timestamp: str
```

### 2. Checkpoint location

`.action-harness/checkpoints/<run-id>.json` — same directory pattern as manifests. One file per run. Written atomically (temp file + rename) to prevent corruption.

### 3. Checkpoint write points

After each of these stages completes:
- Worktree creation
- Worker dispatch (including retries)
- Eval pass
- PR creation
- Review rounds
- OpenSpec review

The checkpoint is written by a `_write_checkpoint()` helper called at each transition point in `_run_pipeline_inner()`.

### 4. Resume flow

```
harness run --change X --repo . --resume latest
  │
  ├─ Find latest checkpoint for change X
  ├─ Read checkpoint
  ├─ Verify worktree still exists (if not, start fresh)
  ├─ Skip to current_stage
  └─ Continue pipeline from there
```

If `--resume` is provided but no checkpoint exists, log a warning and start fresh. If the worktree was cleaned up (e.g., temp dir deleted), start fresh from worktree stage.

### 5. `--resume latest` vs `--resume <run-id>`

`--resume latest` finds the most recent checkpoint for the given change name. `--resume <run-id>` resumes a specific run. Both validate that the checkpoint matches the `--change` and `--repo` arguments.

### 6. Cleanup

On successful pipeline completion (manifest written), delete the checkpoint file. Failed runs leave the checkpoint for future resume.

## Risks / Trade-offs

- [Stale worktree] The worktree might not exist after a crash (temp dir cleaned by OS) → Mitigation: checkpoint validation checks `worktree_path` exists. If not, start fresh.
- [Checkpoint corruption] Process killed mid-write → Mitigation: atomic write (temp + rename).
- [State drift] Code changed on main between crash and resume → Mitigation: checkpoint stores the branch name. If the branch still exists with the expected commits, resume is safe. If not, start fresh.
