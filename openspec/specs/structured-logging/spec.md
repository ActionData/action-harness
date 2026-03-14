# structured-logging Specification

## Purpose
TBD - created by archiving change structured-logging. Update Purpose after archive.
## Requirements
### Requirement: Event schema
Every structured log event SHALL be a JSON object containing at minimum: `timestamp` (ISO 8601 string), `event` (string identifying the event type), and `run_id` (string identifying the pipeline run). Events MAY include additional fields: `stage` (string), `duration_seconds` (float), `success` (bool), and `metadata` (object with event-specific key-value pairs).

#### Scenario: Event contains required fields
- **WHEN** any event is emitted during a pipeline run
- **THEN** the JSON object MUST contain `timestamp`, `event`, and `run_id` fields

#### Scenario: Timestamp is ISO 8601 UTC
- **WHEN** an event is emitted
- **THEN** the `timestamp` field MUST be an ISO 8601 string with UTC timezone

#### Scenario: Event type is a known string
- **WHEN** an event is emitted
- **THEN** the `event` field MUST be one of the defined event types: `run.started`, `run.completed`, `worktree.created`, `worktree.failed`, `worker.dispatched`, `worker.completed`, `worker.failed`, `eval.started`, `eval.command.passed`, `eval.command.failed`, `eval.completed`, `retry.scheduled`, `pr.created`, `pr.failed`, `openspec_review.completed`, `pipeline.error`

### Requirement: Event log file
The pipeline SHALL write all events for a run to a JSON-lines file at `.action-harness/runs/<run-timestamp>-<change-name>.events.jsonl`, using the same naming convention as the run manifest. Each line in the file SHALL be a single JSON object followed by a newline character.

#### Scenario: Event log file is created on pipeline start
- **WHEN** the pipeline starts a run
- **THEN** a `.events.jsonl` file SHALL be created in `.action-harness/runs/`

#### Scenario: Event log file uses same naming as manifest
- **WHEN** a pipeline run completes and produces both a manifest and an event log
- **THEN** the event log filename SHALL match the manifest filename except with `.events.jsonl` suffix instead of `.json`

#### Scenario: Each line is valid JSON
- **WHEN** the event log file is read after a run completes
- **THEN** every line in the file SHALL parse as valid JSON

### Requirement: Run lifecycle events
The pipeline SHALL emit a `run.started` event when the pipeline begins and a `run.completed` event when the pipeline finishes. The `run.completed` event SHALL include `success` (bool), `duration_seconds` (float), `retries` (int), and `error` (string or null) in its metadata.

#### Scenario: Run started event emitted first
- **WHEN** the pipeline begins execution
- **THEN** the first event in the log file SHALL be `run.started` with `metadata.change_name` set to the change being processed

#### Scenario: Run completed event emitted last
- **WHEN** the pipeline finishes execution (success or failure)
- **THEN** the last event in the log file SHALL be `run.completed` with `metadata.success`, `metadata.duration_seconds`, and `metadata.retries`

#### Scenario: Run completed on unexpected error
- **WHEN** the pipeline catches an unexpected exception
- **THEN** a `run.completed` event SHALL still be emitted with `success` set to false and `metadata.error` containing the error message

### Requirement: Worktree events
The pipeline SHALL emit a `worktree.created` event when worktree creation succeeds, or a `worktree.failed` event when it fails. Both events SHALL set `stage` to `"worktree"`.

#### Scenario: Worktree creation success
- **WHEN** `create_worktree` returns a successful `WorktreeResult`
- **THEN** a `worktree.created` event SHALL be emitted with `metadata.branch` and `metadata.worktree_path`

#### Scenario: Worktree creation failure
- **WHEN** `create_worktree` returns a failed `WorktreeResult`
- **THEN** a `worktree.failed` event SHALL be emitted with `metadata.error`

### Requirement: Worker events
The pipeline SHALL emit a `worker.dispatched` event before calling `dispatch_worker` and a `worker.completed` or `worker.failed` event after it returns. Worker events SHALL set `stage` to `"worker"`.

#### Scenario: Worker dispatch event
- **WHEN** the pipeline is about to call `dispatch_worker`
- **THEN** a `worker.dispatched` event SHALL be emitted with `metadata.attempt` (0-indexed attempt number)

#### Scenario: Worker success event
- **WHEN** `dispatch_worker` returns a successful `WorkerResult`
- **THEN** a `worker.completed` event SHALL be emitted with `metadata.commits_ahead`, `metadata.cost_usd`, and `duration_seconds`

#### Scenario: Worker failure event
- **WHEN** `dispatch_worker` returns a failed `WorkerResult`
- **THEN** a `worker.failed` event SHALL be emitted with `metadata.error` and `duration_seconds`

### Requirement: Eval events
The pipeline SHALL emit an `eval.started` event before running eval, per-command result events (`eval.command.passed` or `eval.command.failed`), and an `eval.completed` event when all eval commands finish or one fails. Eval events SHALL set `stage` to `"eval"`.

#### Scenario: Eval started event
- **WHEN** the pipeline is about to call `run_eval`
- **THEN** an `eval.started` event SHALL be emitted with `metadata.command_count` set to the number of eval commands

#### Scenario: Per-command pass event
- **WHEN** an eval command exits with code 0
- **THEN** an `eval.command.passed` event SHALL be emitted with `metadata.command` set to the command string

#### Scenario: Per-command fail event
- **WHEN** an eval command exits with a nonzero code
- **THEN** an `eval.command.failed` event SHALL be emitted with `metadata.command` and `metadata.exit_code`

#### Scenario: Eval completed event
- **WHEN** all eval commands finish or one fails
- **THEN** an `eval.completed` event SHALL be emitted with `metadata.commands_passed`, `metadata.commands_run`, and `success`

### Requirement: Retry events
The pipeline SHALL emit a `retry.scheduled` event when it decides to retry after a worker or eval failure.

#### Scenario: Retry after eval failure
- **WHEN** eval fails and the pipeline has retries remaining
- **THEN** a `retry.scheduled` event SHALL be emitted with `metadata.attempt` (the upcoming attempt number), `metadata.reason` (`"eval_failed"` or `"worker_failed"`), and `metadata.max_retries`

### Requirement: PR events
The pipeline SHALL emit a `pr.created` event when PR creation succeeds, or a `pr.failed` event when it fails. PR events SHALL set `stage` to `"pr"`.

#### Scenario: PR created event
- **WHEN** `create_pr` returns a successful `PrResult`
- **THEN** a `pr.created` event SHALL be emitted with `metadata.pr_url` and `metadata.branch`

#### Scenario: PR creation failure event
- **WHEN** `create_pr` returns a failed `PrResult`
- **THEN** a `pr.failed` event SHALL be emitted with `metadata.error`

### Requirement: OpenSpec review events
The pipeline SHALL emit an `openspec_review.completed` event after the OpenSpec review stage finishes.

#### Scenario: Review completed event
- **WHEN** the OpenSpec review stage finishes
- **THEN** an `openspec_review.completed` event SHALL be emitted with `metadata.success`, `metadata.archived`, `metadata.findings` (list of strings), and `duration_seconds`

### Requirement: Pipeline error events
The pipeline SHALL emit a `pipeline.error` event when an unexpected exception is caught in the top-level error handler.

#### Scenario: Unexpected exception
- **WHEN** `run_pipeline` catches an unexpected exception in its `except Exception` handler
- **THEN** a `pipeline.error` event SHALL be emitted with `metadata.error` containing the exception message, before the `run.completed` event

### Requirement: Existing stderr logging preserved
The addition of structured logging SHALL NOT remove or alter any existing `typer.echo(..., err=True)` calls. Structured events are emitted in addition to existing stderr output.

#### Scenario: Stderr output unchanged
- **WHEN** a pipeline run executes with structured logging active
- **THEN** all existing stderr log lines (e.g., `[pipeline] starting for change ...`, `[eval] running ...`) SHALL still be emitted to stderr

### Requirement: Event log path in manifest
The `RunManifest` model SHALL include an `event_log_path` field (string or null) that records the absolute path to the event log file for the run.

#### Scenario: Manifest references event log
- **WHEN** a pipeline run completes and the manifest is written
- **THEN** `manifest.event_log_path` SHALL contain the path to the `.events.jsonl` file

### Requirement: Event emission failure is non-fatal
Failures to emit or write events SHALL NOT cause the pipeline to fail. Event emission errors SHALL be logged to stderr as warnings and the pipeline SHALL continue.

#### Scenario: Disk write failure during event emission
- **WHEN** writing an event to the log file raises an I/O error
- **THEN** the pipeline SHALL log a warning to stderr and continue without the event

