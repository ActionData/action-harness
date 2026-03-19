## ADDED Requirements

### Requirement: Repo assess skill
The system SHALL provide a Claude Code command at `action:repo-assess` that runs `uv run action-harness assess --repo .` in the foreground and displays the assessment output directly.

#### Scenario: Run assessment
- **WHEN** the user invokes `/action:repo-assess`
- **THEN** the system runs the assess command and displays category scores and overall score

### Requirement: Repo ready skill
The system SHALL provide a Claude Code command at `action:repo-ready` that runs `uv run action-harness ready --repo .` in the foreground and displays which changes are ready for implementation.

#### Scenario: Check ready changes
- **WHEN** the user invokes `/action:repo-ready`
- **THEN** the system runs the ready command and displays ready and blocked changes

### Requirement: Repo report skill
The system SHALL provide a Claude Code command at `action:repo-report` that runs `uv run action-harness report --repo .` in the foreground and displays recent run history and failure trends.

#### Scenario: View run report
- **WHEN** the user invokes `/action:repo-report`
- **THEN** the system runs the report command and displays recent run summaries
