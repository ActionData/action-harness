## ADDED Requirements

### Requirement: Dispatch change skill
The system SHALL provide a Claude Code command at `action:dispatch-change` that dispatches a harness run for a named OpenSpec change. The command SHALL invoke `uv run action-harness run --change <name> --repo . --auto-merge --wait-for-ci` via the Bash tool with `run_in_background: true`. The command SHALL accept optional flag overrides appended after the change name.

#### Scenario: Dispatch a change by name
- **WHEN** the user or agent invokes `/action:dispatch-change deduplicate-run-stats`
- **THEN** the system runs `uv run action-harness run --change deduplicate-run-stats --repo . --auto-merge --wait-for-ci` in the background and confirms the dispatch with the task ID

#### Scenario: Dispatch with flag override
- **WHEN** the user invokes `/action:dispatch-change my-change --no-auto-merge`
- **THEN** the system runs the command without `--auto-merge` but retains `--wait-for-ci`

#### Scenario: No change name provided
- **WHEN** the user invokes `/action:dispatch-change` without arguments
- **THEN** the system asks the user which change to dispatch

### Requirement: Dispatch prompt skill
The system SHALL provide a Claude Code command at `action:dispatch-prompt` that dispatches a harness run with a freeform prompt. The command SHALL invoke `uv run action-harness run --prompt "<prompt>" --repo . --auto-merge --wait-for-ci` via the Bash tool with `run_in_background: true`.

#### Scenario: Dispatch with a freeform prompt
- **WHEN** the user invokes `/action:dispatch-prompt fix the ruff lint errors in cli.py`
- **THEN** the system runs `uv run action-harness run --prompt "fix the ruff lint errors in cli.py" --repo . --auto-merge --wait-for-ci` in the background

#### Scenario: No prompt provided
- **WHEN** the user invokes `/action:dispatch-prompt` without arguments
- **THEN** the system asks the user what prompt to dispatch

### Requirement: Dispatch issue skill
The system SHALL provide a Claude Code command at `action:dispatch-issue` that dispatches a harness run from a GitHub issue number. The command SHALL invoke `uv run action-harness run --issue <number> --repo . --auto-merge --wait-for-ci` via the Bash tool with `run_in_background: true`.

#### Scenario: Dispatch from an issue number
- **WHEN** the user invokes `/action:dispatch-issue 42`
- **THEN** the system runs `uv run action-harness run --issue 42 --repo . --auto-merge --wait-for-ci` in the background

#### Scenario: No issue number provided
- **WHEN** the user invokes `/action:dispatch-issue` without arguments
- **THEN** the system asks the user which issue to dispatch
