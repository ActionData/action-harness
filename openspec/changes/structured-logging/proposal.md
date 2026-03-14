## Why

The harness currently emits human-readable log lines to stderr via `typer.echo(..., err=True)`. These are useful for interactive debugging but cannot be programmatically consumed. As the harness moves toward self-hosting, it needs machine-parseable observability: a JSON event stream that captures every stage transition, dispatch, eval result, retry decision, and error as it happens. The run manifest already captures final stage results, but it is written only at the end of a run. Structured logging provides real-time visibility during execution, which is the foundation for failure reporting, live progress feeds, and the always-on server mode on the roadmap.

## What Changes

- Add a new `event_log` module that emits JSON-lines events to a per-run log file alongside the manifest.
- Define a standard event schema: timestamp, event type, stage, duration (where applicable), and a metadata dict for event-specific fields.
- Emit events at every stage boundary in the pipeline: run start, worktree created, worker dispatched, worker completed, eval started, eval command result, eval completed, retry decision, PR created, openspec review completed, run completed.
- Write events to `.action-harness/runs/<run-id>.events.jsonl` — the same directory as the manifest, using the same naming convention.
- Existing stderr logging is unchanged. The event log is always-on with no CLI flag required.

## Capabilities

### New Capabilities
- `structured-logging`: JSON-lines event stream emitted during pipeline execution for machine-parseable observability.

### Modified Capabilities
<!-- No existing specs to modify -->

## Impact

- **New file**: `src/action_harness/event_log.py` — event model, emitter, file writer.
- **Modified file**: `src/action_harness/pipeline.py` — emit events at stage boundaries.
- **Modified file**: `src/action_harness/evaluator.py` — emit per-command eval events.
- **Modified file**: `src/action_harness/models.py` — add event log path to `RunManifest`.
- **New tests**: `tests/test_event_log.py` — unit tests for event emission and file writing.
- **No new dependencies**: uses stdlib `json` and `datetime`.
- **No CLI changes**: the event log is always-on, no flag needed.
