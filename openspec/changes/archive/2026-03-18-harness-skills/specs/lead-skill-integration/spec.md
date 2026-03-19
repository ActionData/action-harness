## ADDED Requirements

### Requirement: Lead persona references dispatch skills
The lead persona prompt SHALL reference `/action:dispatch-change`, `/action:dispatch-prompt`, and `/action:dispatch-issue` skills instead of raw `harness run` CLI commands in the "Your Capabilities" and "Implementation Rule" sections.

#### Scenario: Lead dispatches a change
- **WHEN** the lead agent needs to dispatch an OpenSpec change
- **THEN** it uses the `/action:dispatch-change <name>` skill invocation instead of a raw CLI command

#### Scenario: Lead dispatches a prompt
- **WHEN** the lead agent needs to dispatch a freeform task
- **THEN** it uses the `/action:dispatch-prompt <prompt>` skill invocation instead of a raw CLI command

#### Scenario: Lead dispatches from an issue
- **WHEN** the lead agent needs to dispatch from a GitHub issue
- **THEN** it uses the `/action:dispatch-issue <number>` skill invocation instead of a raw CLI command

### Requirement: Lead persona references repo skills
The lead persona prompt SHALL reference `/action:repo-assess`, `/action:repo-ready`, and `/action:repo-report` skills instead of raw CLI commands for repo operations.

#### Scenario: Lead checks assessment
- **WHEN** the lead agent needs to assess the repo
- **THEN** it uses the `/action:repo-assess` skill invocation instead of a raw CLI command
