## Context

The harness pipeline currently has two observability mechanisms:

1. **stderr logging** -- human-readable `typer.echo(..., err=True)` calls scattered across `pipeline.py`, `evaluator.py`, `worker.py`, `worktree.py`, and `pr.py`. These provide real-time output during interactive use.
2. **Run manifest** -- a JSON file written once at the end of a run to `.action-harness/runs/`. Contains final stage results but nothing about intermediate state or timing of individual events.

Structured logging fills the gap: machine-parseable, real-time, per-event records emitted as the pipeline executes. This is the first item on the self-hosted backlog (ROADMAP.md item 1) because downstream capabilities (failure reporting, live progress feeds, always-on server) depend on having a parseable event stream.

The pipeline is deterministic and single-threaded. Events are emitted synchronously in the orchestration layer (`pipeline.py`) and the eval runner (`evaluator.py`). There is no concurrency concern.

## Goals / Non-Goals

**Goals:**
- Emit a JSON-lines event file for every pipeline run with events for all stage transitions, dispatches, eval results, retries, and errors.
- Make the event stream always-on with zero configuration. No CLI flag required.
- Keep existing stderr logging completely intact.
- Make event emission non-fatal: I/O errors writing events must not crash the pipeline.

**Non-Goals:**
- Replacing or modifying existing `typer.echo` stderr output.
- Sending events to external systems (log aggregators, webhooks). File-only for bootstrap.
- Adding a `--log-format` CLI flag. The event log is always written alongside the manifest; stderr output is always human-readable.
- Structured logging inside worker subprocesses (Claude Code CLI). The harness only logs its own orchestration events.
- Query or analysis tooling for event logs. That is `failure-reporting` on the roadmap.

## Decisions

### D1: Always-on file output, no CLI flag

**Decision**: Events are always written to a `.events.jsonl` file. No `--log-format` flag.

**Rationale**: The event log is an observability artifact like the manifest. It costs negligible disk space (a few KB per run). Adding a flag creates a state where the harness sometimes has observability and sometimes does not, which undermines the purpose. The manifest is already always-on; events follow the same pattern.

**Alternative considered**: `--log-format json` flag to write events to stderr instead of human-readable output. Rejected because (a) it would require replacing the current stderr output or multiplexing two formats, (b) downstream consumers (failure-reporting, live-progress-feed) need a file they can read, not ephemeral stderr.

### D2: JSON-lines file alongside the manifest

**Decision**: Write events to `.action-harness/runs/<timestamp>-<change-name>.events.jsonl` using the same naming convention as the manifest JSON file.

**Rationale**: Co-locating events with the manifest makes them easy to correlate. The `.events.jsonl` suffix distinguishes them from the `.json` manifest. JSON-lines (one JSON object per line) is append-friendly and doesn't require buffering the full event list in memory.

**Alternative considered**: Writing events inside the manifest JSON. Rejected because the manifest is written at the end of the run; events need to be written as they happen (crash safety, real-time observability).

### D3: Event model as a Pydantic BaseModel

**Decision**: Define a `PipelineEvent` Pydantic model in `src/action_harness/event_log.py` with fields: `timestamp` (str), `event` (str), `run_id` (str), `stage` (str | None), `duration_seconds` (float | None), `success` (bool | None), `metadata` (dict[str, Any]).

**Rationale**: Pydantic gives us validated serialization consistent with the existing models in `models.py`. Using `model_dump_json()` for serialization ensures consistent output format. Keeping the event model in its own module avoids circular imports since `pipeline.py` already imports from `models.py`.

**Alternative considered**: Plain dict + `json.dumps`. Rejected because it loses validation and is inconsistent with the codebase style (everything else uses Pydantic).

### D4: EventLogger class with context manager protocol

**Decision**: Create an `EventLogger` class that takes a file path, opens it on construction, provides an `emit(event, stage, ...)` method, and closes the file on `close()`. The pipeline creates one `EventLogger` at the start of a run and closes it at the end.

**Rationale**: Encapsulating the file handle in a class avoids passing a file handle through every function. The `emit` method handles timestamp generation, run_id injection, serialization, and I/O error handling in one place. The pipeline holds the logger and calls `emit` at stage boundaries.

**Alternative considered**: Module-level functions with a global file handle. Rejected because global state complicates testing and makes the logger's lifecycle implicit.

### D5: run_id derived from manifest timestamp

**Decision**: The `run_id` is generated from `started_at` (not `completed_at`) using the filesystem-safe transformation, plus the change name (e.g., `2026-03-13T10-00-00-structured-logging`). It is generated once at the start of `run_pipeline` and used for both the event log filename and the manifest filename. This requires updating `_write_manifest` to accept the pre-generated `run_id` instead of computing its own from `completed_at`.

**Rationale**: Using the same identifier for both artifacts makes correlation trivial. Generating it early (before any stage runs) ensures all events share the same run_id. Using `started_at` is necessary because the event log must be opened at run start, before `completed_at` is known.

### D6: Eval per-command events emitted from evaluator.py

**Decision**: The `run_eval` function in `evaluator.py` accepts an optional `EventLogger` parameter and emits `eval.command.passed` / `eval.command.failed` events inside the command loop. The `eval.started` and `eval.completed` events are emitted from `pipeline.py` before and after calling `run_eval`.

**Rationale**: Per-command events require access to the command loop internals (command string, exit code). Passing the logger into `run_eval` is simpler than having `run_eval` return per-command results that the pipeline then converts to events. The `eval.started` / `eval.completed` lifecycle events stay in `pipeline.py` where all other lifecycle events live.

**Alternative considered**: Having `run_eval` return a list of per-command results that `pipeline.py` converts to events. Rejected because it would require a new return type and restructuring the function, and the events are best emitted in real-time as commands run.

### D7: Non-fatal emission with stderr warning

**Decision**: The `emit` method wraps the write in a try/except. On I/O error, it logs a warning via `typer.echo(..., err=True)` and returns without raising. The pipeline continues.

**Rationale**: The event log is an observability artifact. Its failure should not mask the pipeline outcome, consistent with how `_write_manifest` already handles errors.

## Risks / Trade-offs

- **[Risk] Event log grows unbounded for long-running pipelines with many retries** -- Mitigation: Each run produces its own file. The number of events per run is bounded by `max_retries * eval_commands + constant_overhead`, which is small (tens of events). Disk cleanup is a concern for `workspace-management`, not this change.

- **[Risk] Adding `EventLogger` parameter to `run_eval` couples evaluator to logging** -- Mitigation: The parameter is optional (defaults to None). When None, no events are emitted. The evaluator remains fully functional without the logger.

- **[Trade-off] No streaming to external systems** -- Accepted for bootstrap. File-based events are sufficient for self-hosting. External streaming is a natural extension if needed later.

- **[Trade-off] Event types are string constants, not an enum** -- Accepted for simplicity. The spec defines the complete set. An enum adds boilerplate without meaningful safety since events are only emitted from a small number of call sites.

- **[Risk] Event type list will need extension when new pipeline stages are added** -- When `review-agents` or other stages land, new event types (e.g., `review.dispatched`, `review.completed`) will be needed. This is expected and low-cost — add new event types and emit calls in the new stage code.
