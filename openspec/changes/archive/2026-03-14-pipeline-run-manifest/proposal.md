## Why

The pipeline discards all stage results after each run. WorkerResult (cost, duration, output), EvalResult (commands, pass/fail), and WorktreeResult (path, branch) are used for flow control and then lost. When a human reviews a PR or a review agent needs context about what happened, there's no structured record — just the PR body (sparse) and stderr (ephemeral).

This blocks review agents (which need to know what the pipeline did), enriched PR descriptions (which need stage results to build the body), and failure analysis (which needs historical run data). The run manifest is the foundation these features build on.

## What Changes

- Collect all stage results during the pipeline run into a `RunManifest` Pydantic model
- Write the manifest as JSON to `.action-harness/runs/<timestamp>-<change-name>.json` in the repo after the run completes (success or failure)
- Make the manifest available to downstream consumers (PR body builder, review agents)
- The pipeline function returns the manifest alongside the PrResult

## Capabilities

### New Capabilities

- `run-manifest`: Pipeline run manifest — collects all stage results into a structured JSON file persisted per run. Contains timestamps, stage results, cost, duration, retries, eval details, and final outcome.

### Modified Capabilities

## Impact

- `src/action_harness/models.py` — new `RunManifest` model
- `src/action_harness/pipeline.py` — collect results, write manifest, return it
- `.action-harness/runs/` directory in the repo (gitignored)
- `.gitignore` — add `.action-harness/`
- `enrich-pr-description` can read the manifest instead of threading individual results
- `openspec-review-agent` can read the manifest for run context
