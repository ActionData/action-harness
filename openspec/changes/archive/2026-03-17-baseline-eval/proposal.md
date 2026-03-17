## Why

The harness runs eval commands (lint, format, tests) on the entire repo, not just the worker's changes. If the repo has pre-existing lint or format failures, the worker spends retry rounds fixing issues it didn't create. On the analytics-monorepo run, 2 of 3 retries were spent fixing pre-existing ruff check and ruff format failures across 21 files the worker never touched.

The harness should establish a baseline before the worker starts, so eval only catches regressions introduced by the worker's changes.

## What Changes

- Run eval commands before the worker starts to establish a baseline (which commands pass, which fail)
- After the worker completes, only fail on commands that were passing at baseline but now fail (regressions)
- Commands that were already failing at baseline are noted but don't block
- Alternatively, scope lint/format checks to only changed files when the tool supports it

## Capabilities

### New Capabilities

- `baseline-eval`: Run eval before worker dispatch to establish baseline. Post-worker eval only fails on regressions, not pre-existing issues.

### Modified Capabilities

## Impact

- `src/action_harness/evaluator.py` — add baseline eval run, compare against post-worker results
- `src/action_harness/pipeline.py` — run baseline eval before worker dispatch
- `src/action_harness/models.py` — add baseline info to EvalResult or manifest
