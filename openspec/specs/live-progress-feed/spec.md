# live-progress-feed Specification

## Purpose
TBD - created by archiving change live-progress-feed. Update Purpose after archive.
## Requirements
### Requirement: Progress command tails event log
The `harness progress --repo <path>` command SHALL tail the most recent `.events.jsonl` file and display pipeline events as they occur.

#### Scenario: Live progress during a run
- **WHEN** a pipeline is running and the user runs `harness progress --repo .`
- **THEN** the command SHALL display events as they are written, with elapsed time and formatted details

#### Scenario: Completed run
- **WHEN** no pipeline is running and the user runs `harness progress --repo .`
- **THEN** the command SHALL display the most recent completed run's events and exit

#### Scenario: No event logs
- **WHEN** no `.events.jsonl` files exist in `.action-harness/runs/`
- **THEN** the command SHALL output "No event logs found" and exit

### Requirement: Human-readable formatting
Each event SHALL be displayed as `[MM:SS] event_name — key details` where `MM:SS` is elapsed time since `run.started`.

#### Scenario: Worker completed event
- **WHEN** a `worker.completed` event is received with `commits_ahead=5` and `context_usage_pct=0.03`
- **THEN** the display SHALL show `[MM:SS] worker.completed — 5 commit(s), context: 3%`

#### Scenario: Eval completed event
- **WHEN** an `eval.completed` event is received with `commands_passed=5` and `commands_run=5`
- **THEN** the display SHALL show `[MM:SS] eval.completed — 5/5 passed`

### Requirement: Graceful handling of unparseable lines
When a line in the event log cannot be parsed as valid JSON, the tailer SHALL skip it with a warning and continue processing subsequent lines.

#### Scenario: Partial line during live tailing
- **WHEN** a line cannot be parsed as JSON (partial write, corrupt data)
- **THEN** the tailer SHALL log a warning to stderr and continue to the next line

### Requirement: Elapsed time fallback
When `run.started` has not been seen (e.g., tailing mid-run), elapsed time SHALL fall back to wall-clock time from the event's timestamp.

#### Scenario: No run.started event
- **WHEN** the first event seen is `worker.completed` (run.started was before the tail started)
- **THEN** the display SHALL show the event's wall-clock time `[HH:MM:SS]` instead of elapsed `[MM:SS]`

### Requirement: --run flag follows specific run
The `--run <run-id>` flag SHALL tail the event log for a specific run instead of the latest.

#### Scenario: Specific run
- **WHEN** the user runs `harness progress --repo . --run 2026-03-17T01-00-00-change-name`
- **THEN** the command SHALL tail that specific run's `.events.jsonl` file

#### Scenario: Run not found
- **WHEN** the specified run ID does not have an event log
- **THEN** the command SHALL output "Event log not found for run: <id>" and exit

### Requirement: --json streams raw events
The `--json` flag SHALL output each event as a raw JSON line (same format as the source file).

#### Scenario: JSON output
- **WHEN** the user runs `harness progress --repo . --json`
- **THEN** each line of stdout SHALL be a valid JSON object matching the `PipelineEvent` schema

### Requirement: Clean exit on run completion
The command SHALL exit when a `run.completed` or `pipeline.error` event is received.

#### Scenario: Successful completion
- **WHEN** a `run.completed` event with `success=True` is received
- **THEN** the command SHALL print a summary line and exit with code 0

#### Scenario: Pipeline error
- **WHEN** a `pipeline.error` event is received
- **THEN** the command SHALL print the error and exit with code 1

