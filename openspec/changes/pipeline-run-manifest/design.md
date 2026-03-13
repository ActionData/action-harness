## Context

The pipeline runs stages sequentially and each returns a Pydantic `StageResult` subclass. These results are checked for success/failure, used for retry decisions, then discarded. The only surviving artifact is the `PrResult` returned to the CLI. All intermediate data (worker cost, eval timing, retry history) is lost.

Every downstream feature (enriched PR body, review agents, failure reporting) needs access to what happened during the run. Threading individual results to each consumer doesn't scale. A single manifest document solves this for all consumers.

## Goals / Non-Goals

**Goals:**
- Capture all stage results in a single structured document per run
- Persist to disk so it survives process exit
- Make it available to the PR body builder and review agents
- Include enough detail to reconstruct what happened without re-running

**Non-Goals:**
- Real-time streaming (that's structured-logging)
- Cross-run aggregation or dashboards (that's failure-reporting)
- Storing the manifest in git (it's a local artifact, gitignored)

## Decisions

### 1. RunManifest as a Pydantic model containing all stage results

Define `RunManifest(BaseModel)` with fields: `change_name`, `repo_path`, `started_at`, `completed_at`, `success`, `stages` (list of stage results), `total_duration_seconds`, `total_cost_usd`, `retries`, `pr_url`, `error`. Each stage result is already a Pydantic model — the manifest just collects them.

**Why:** Pydantic models serialize to JSON with `.model_dump_json()`. No custom serialization needed. Type-safe, IDE-friendly, consistent with existing patterns.

### 2. Write to `.action-harness/runs/` in the repo directory

Save manifests to `<repo>/.action-harness/runs/<ISO-timestamp>-<change-name>.json`. Create the directory if it doesn't exist. Add `.action-harness/` to `.gitignore`.

**Why:** Local to the repo, not global. Each repo accumulates its own run history. Gitignored because manifests are operational artifacts, not source code. The directory is discoverable by agents working in the repo.

### 3. Pipeline collects results and builds manifest incrementally

As each stage completes, append its result to a list. After the run (success or failure), build the `RunManifest` and write it. The pipeline function returns both `PrResult` and `RunManifest`.

**Why:** Incremental collection means the manifest captures everything even on failure — you see exactly which stage failed and what happened before it.

### 4. Return manifest from run_pipeline alongside PrResult

Change `run_pipeline` return type to a tuple `(PrResult, RunManifest)` or add a `manifest` field to `PrResult`. The CLI can log the manifest path. Downstream consumers (PR body, review agents) receive the manifest directly.

**Why:** The manifest is the canonical record of the run. Every consumer should get it from the pipeline, not reconstruct it from scattered results.

### 5. Manifest written on both success and failure

The manifest is always written, regardless of outcome. Failed runs are as important to record as successful ones — more so, since they're what gets debugged.

**Why:** A missing manifest for a failed run is the worst case. Always write.

## Risks / Trade-offs

**[Risk] Manifest files accumulate on disk.**
→ Mitigation: Acceptable for bootstrap. A future `action-harness clean` command can prune old manifests. Each manifest is small (a few KB).

**[Trade-off] Changing run_pipeline return type is a breaking change.**
→ Mitigation: Only the CLI calls `run_pipeline` today. Update it in the same PR.
