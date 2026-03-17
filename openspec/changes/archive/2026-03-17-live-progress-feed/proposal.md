## Why

When the harness runs, the operator has no visibility into what's happening. Pipeline runs take 30-60 minutes and the only output is stderr log lines mixed with the claude CLI's own output. The operator resorts to polling `ps` and `tail` on output files to check progress.

The event log (`.events.jsonl`) already writes structured events at every stage boundary in real-time. A progress feed command can tail this file and present a live, human-readable view of the pipeline's progress.

## What Changes

- New CLI command: `harness progress --repo <path>` that tails the most recent `.events.jsonl` file and displays live pipeline progress
- Shows: current stage, elapsed time, worker status, eval results, review findings count, cost so far
- `--run <run-id>` to follow a specific run instead of the latest
- `--json` for machine-readable streaming output (one JSON event per line)
- Exits when the run completes (detects `run.completed` event)

## Capabilities

### New Capabilities
- `live-progress-feed`: Real-time CLI display of pipeline progress by tailing the event log file.

### Modified Capabilities
None — reads existing event log files, no pipeline changes needed.

## Impact

- `cli.py` — new `progress` command
- New module `src/action_harness/progress_feed.py` — event log tailing and formatting
- Reads existing `.action-harness/runs/<run-id>.events.jsonl` files (no schema changes)
- No changes to pipeline, worker, or event logger
