# session-resume Specification

## Purpose
Session resume allows the harness to continue worker sessions across retries using Claude CLI's `--resume` flag, preserving context and reducing cost when the context window is not exhausted.

## Requirements

### Requirement: Capture session_id from worker dispatch
The harness SHALL capture the `session_id` field from the Claude CLI JSON output after each worker dispatch and store it on the `WorkerResult` model.

#### Scenario: Session ID captured on successful dispatch
- **WHEN** the Claude CLI returns JSON output with a `session_id` field
- **THEN** `WorkerResult.session_id` SHALL contain the session ID string

#### Scenario: Session ID captured on failed dispatch
- **WHEN** the Claude CLI returns JSON output with `session_id` but the dispatch fails (e.g., no commits)
- **THEN** `WorkerResult.session_id` SHALL still contain the session ID (the session is valid even if the outcome wasn't)

#### Scenario: No session ID in output
- **WHEN** the Claude CLI output does not contain a `session_id` field
- **THEN** `WorkerResult.session_id` SHALL be None

### Requirement: Resume worker session on eval-failure retry
When retrying after an eval failure, the harness SHALL use `--resume <session_id>` from the prior `WorkerResult` if a session ID is available and context usage is below the threshold.

#### Scenario: Eval retry with resume
- **WHEN** eval fails and the prior `WorkerResult` has a `session_id` and context usage is below 60%
- **THEN** the retry dispatch SHALL include `--resume <session_id>` and the user prompt SHALL be the eval feedback only (not the full opsx:apply instruction)

#### Scenario: Eval retry without resume (context exhausted)
- **WHEN** eval fails and the prior dispatch used more than 60% of the context window
- **THEN** the retry dispatch SHALL be a fresh dispatch with the eval feedback as the user prompt (current behavior)

#### Scenario: Eval retry without resume (no session ID)
- **WHEN** eval fails and the prior `WorkerResult` has `session_id: None`
- **THEN** the retry dispatch SHALL be a fresh dispatch (current behavior)

### Requirement: Resume worker session on review fix-retry
When retrying after review findings, the harness SHALL use `--resume <session_id>` from the last successful worker dispatch so the original worker addresses its own findings.

#### Scenario: Review fix-retry with resume
- **WHEN** review findings require fixes and the last successful `WorkerResult` has a `session_id`
- **THEN** the fix-retry dispatch SHALL include `--resume <session_id>` and the user prompt SHALL be the review feedback

#### Scenario: Review fix-retry fallback
- **WHEN** the last successful `WorkerResult` has no `session_id` or `--resume` fails
- **THEN** the fix-retry SHALL fall back to a fresh dispatch with review feedback (current behavior)

### Requirement: Graceful fallback on resume failure
If `--resume` fails for any reason (expired session, CLI error), the harness SHALL fall back to a fresh dispatch with feedback. The failure SHALL be logged as a warning, not an error.

#### Scenario: Resume fails with CLI error
- **WHEN** the claude CLI returns a non-zero exit code when using `--resume`
- **THEN** the harness SHALL log a warning, discard the session ID, and retry as a fresh dispatch with the same feedback. The fallback fresh dispatch SHALL NOT count as an additional retry attempt.

### Requirement: Resume requires feedback
When `session_id` is provided to `dispatch_worker()`, `feedback` MUST also be provided. Resume without feedback is a programming error.

#### Scenario: Resume without feedback raises error
- **WHEN** `dispatch_worker()` is called with `session_id` set but `feedback` is None
- **THEN** the function SHALL raise a `ValueError("resume requires feedback")`

#### Scenario: Resume succeeds
- **WHEN** the claude CLI returns successfully with `--resume`
- **THEN** the harness SHALL use the new `session_id` from the resumed dispatch for subsequent retries

#### Scenario: Chained resumes across multiple retries
- **WHEN** retry 1 resumes `session_id_a` and produces `session_id_b`, and retry 2 is needed
- **THEN** retry 2 SHALL use `session_id_b` (not `session_id_a`)

#### Scenario: Resume failure scope
- **WHEN** the claude CLI returns a non-zero exit code when using `--resume`
- **THEN** the harness SHALL treat ANY non-zero exit code as a resume failure and fall back to fresh dispatch. The harness does not distinguish session-specific errors from general worker errors in the resume path — the fallback is always to retry fresh.

### Requirement: Store context usage on WorkerResult
The harness SHALL compute and store `context_usage_pct` on `WorkerResult` after each dispatch. This field SHALL survive JSON serialization through `RunManifest`.

#### Scenario: context_usage_pct roundtrip through RunManifest
- **WHEN** a `RunManifest` containing a `WorkerResult` with `context_usage_pct=0.45` is serialized via `model_dump_json()` and deserialized via `model_validate_json()`
- **THEN** the deserialized `WorkerResult.context_usage_pct` SHALL equal `0.45`

### Requirement: Context usage tracking for resume decisions
The harness SHALL compute context usage percentage from the Claude CLI JSON output to decide whether to resume or start fresh.

#### Scenario: Context usage below threshold
- **WHEN** the prior dispatch's `(usage.input_tokens + usage.output_tokens)` is less than 60% of the first model's `contextWindow` in `modelUsage`
- **THEN** the harness SHALL attempt `--resume` on the next retry

#### Scenario: Context usage above threshold
- **WHEN** the prior dispatch's `(usage.input_tokens + usage.output_tokens)` exceeds 60% of the context window
- **THEN** the harness SHALL use a fresh dispatch on the next retry and log "context usage {pct}% exceeds threshold, using fresh dispatch"

### Requirement: Omit --system-prompt on resumed dispatches
When using `--resume`, the harness SHALL NOT pass `--system-prompt` to the Claude CLI (the resumed session already has it).

#### Scenario: Resumed dispatch omits system prompt
- **WHEN** the harness dispatches with `--resume <session_id>`
- **THEN** the CLI command SHALL NOT include the `--system-prompt` flag
