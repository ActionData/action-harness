# agent-assessment Specification

## Purpose
TBD - created by archiving change codebase-assessment. Update Purpose after archive.
## Requirements
### Requirement: Assessment agent is a read-only Claude Code dispatch
The assessment agent SHALL be dispatched as a Claude Code worker with read-only tool access (Read, Glob, Grep, Bash). It SHALL NOT have access to Edit or Write tools. It SHALL NOT produce commits.

#### Scenario: Agent dispatch with restricted tools
- **WHEN** the assessment agent is dispatched with `--deep`
- **THEN** the Claude CLI invocation SHALL include `--allowedTools "Read,Glob,Grep,Bash"` and SHALL NOT include Edit or Write

#### Scenario: Agent produces no commits
- **WHEN** the assessment agent completes
- **THEN** the harness SHALL NOT check for commits (unlike the coder worker)

### Requirement: Assessment agent receives mechanical signals as input
The assessment agent SHALL receive the mechanical scan results as structured JSON in its prompt, so it can focus on quality judgment rather than re-scanning.

#### Scenario: Mechanical signals included in prompt
- **WHEN** the assessment agent is dispatched
- **THEN** its user prompt SHALL contain the mechanical signals JSON and instructions for which categories to assess

### Requirement: Assessment agent produces structured JSON output
The assessment agent SHALL output a JSON response conforming to the following schema:

```json
{
  "categories": {
    "<category_name>": {
      "score_adjustment": <int between -20 and +20>,
      "rationale": "<string explaining the adjustment>",
      "gaps": [
        {
          "severity": "high" | "medium" | "low",
          "finding": "<string describing the gap>",
          "proposal_name": "<kebab-case string>" | null
        }
      ]
    }
  }
}
```

The `categories` object SHALL contain keys for each of the six categories: `context`, `testability`, `ci_guardrails`, `observability`, `tooling`, `isolation`. Each category SHALL have `score_adjustment` (int, clamped to ±20 by the harness), `rationale` (string), and `gaps` (array of gap objects).

#### Scenario: Successful assessment output
- **WHEN** the assessment agent completes successfully
- **THEN** its output SHALL be parseable JSON with a `categories` object containing all six category keys, each with `score_adjustment` (int), `rationale` (string), and `gaps` (array)

#### Scenario: Agent output example
- **WHEN** the agent assesses a repo with good tests but weak documentation
- **THEN** the output SHALL include `"testability": {"score_adjustment": 10, "rationale": "Tests cover error paths and use fixtures well", "gaps": []}` and `"context": {"score_adjustment": -15, "rationale": "README has no architecture overview", "gaps": [{"severity": "medium", "finding": "README lacks architecture section", "proposal_name": "improve-readme"}]}`

#### Scenario: Assessment agent failure
- **WHEN** the assessment agent fails or produces unparseable output
- **THEN** the harness SHALL fall back to mechanical-only scores and log a warning

### Requirement: Assessment agent judges quality not just presence
The assessment agent SHALL read actual source files, test files, and documentation to assess quality beyond what mechanical signals can detect.

#### Scenario: Test quality assessment
- **WHEN** the assessment agent evaluates testability
- **THEN** it SHALL read sample test files and assess whether tests have meaningful assertions, cover error paths, and include integration tests — not just count test functions

#### Scenario: Documentation quality assessment
- **WHEN** the assessment agent evaluates context
- **THEN** it SHALL read CLAUDE.md, README, and key source files to assess whether documentation is clear enough for an autonomous agent to orient itself

#### Scenario: CI quality assessment
- **WHEN** the assessment agent evaluates CI guardrails
- **THEN** it SHALL review CI workflow contents to assess whether steps are comprehensive vs superficial (e.g., a test step that actually runs the test suite vs one that just echoes success)

