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
    completed_stage: str  # last FULLY completed macro-stage
    worktree_path: str | None
    branch: str | None
    pr_url: str | None
    session_id: str | None  # for session-resume on retry
    last_worker_result: WorkerResult | None
    last_eval_result: EvalResult | None
    protected_files: list[str]
    stages: list[StageResultUnion]  # accumulated results
    timestamp: str
    ecosystem: str  # for catalog/review agent injection
    branch_head_sha: str | None  # for state drift validation
    # CLI flags that must match on resume:
    auto_merge: bool = False
    skip_review: bool = False
    review_cycle: list[str] | None = None
```

**Macro-stage progression:** Checkpoints are written at coarse-grained stage boundaries, not within the retry loop. The stages are:

```
worktree → worker_eval → pr → review → openspec_review → merge
```

`worker_eval` is a single macro-stage that encompasses the entire worker+eval retry loop. If the pipeline crashes mid-retry, resume re-runs the entire worker_eval stage from the beginning (with session-resume providing context continuity). This avoids the complexity of restoring retry loop state (`attempt`, `feedback`, `prior_worker_result`).

This is the right tradeoff: the worker_eval stage is the most expensive, but session-resume already handles within-stage continuity. What checkpoint-resume saves is the cost of re-doing PR creation, review rounds, and openspec review — which collectively take longer than a single worker dispatch.

### 2. Checkpoint location

`.action-harness/checkpoints/<run-id>.json` — same directory pattern as manifests. One file per run. Written atomically (temp file + rename) to prevent corruption.

### 3. Checkpoint write points and skip mechanism

Checkpoints are written at 5 macro-stage boundaries in `_run_pipeline_inner()`:
1. After worktree creation → `completed_stage = "worktree"`
2. After the worker+eval retry loop produces eval pass → `completed_stage = "worker_eval"`
3. After PR creation → `completed_stage = "pr"`
4. After the review cycle completes → `completed_stage = "review"`
5. After OpenSpec review → `completed_stage = "openspec_review"`

The skip mechanism: each stage block in `_run_pipeline_inner` is wrapped in a guard:
```python
if _should_run_stage("worktree", checkpoint):
    # worktree creation code
    _write_checkpoint(...)
else:
    # restore locals from checkpoint
    worktree_path = Path(checkpoint.worktree_path)
    branch = checkpoint.branch
```

The `_should_run_stage(stage, checkpoint)` function returns True if `checkpoint` is None or if `stage` comes after `checkpoint.completed_stage` in the stage progression order.

### 3a. Variable restoration on resume

When skipping a stage, the pipeline must restore local variables that subsequent stages depend on. The full mapping:

| Checkpoint field | Pipeline local | Used by |
|---|---|---|
| `worktree_path` | `worktree_path: Path` | all subsequent stages |
| `branch` | `branch: str` | PR creation, cleanup |
| `last_worker_result` | `worker_result: WorkerResult` | PR creation, review fix-retry |
| `last_eval_result` | `eval_result: EvalResult` | PR creation |
| `pr_url` | `pr_result.pr_url` | review agents, merge |
| `session_id` | `resume_session_id` | review fix-retry |
| `protected_files` | `protected_files` | auto-merge gate |
| `stages` | `stages: list[StageResultUnion]` | manifest builder |
| `ecosystem` | `ecosystem` | catalog, review agents |

Variables NOT restored (recomputed or defaulted): `feedback = None`, `attempt = 0`, `prior_worker_result = None`, `findings_remain = False`, `acknowledged = []`, `latest_review_results = []`.

### 3b. CLI flags captured in checkpoint

These CLI flags affect pipeline behavior and must match on resume:
- `auto_merge`, `skip_review`, `review_cycle` — stored in checkpoint
- On resume, the checkpoint's values are used (user does NOT re-specify them)
- If the user provides conflicting flags on resume, log a warning and use the checkpoint's values

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
- [State drift] Code changed on branch between crash and resume → Mitigation: checkpoint stores `branch_head_sha`. On resume, compare against the actual HEAD of the branch. If they match, resume. If they differ (someone pushed to the branch), log a warning and start fresh.
