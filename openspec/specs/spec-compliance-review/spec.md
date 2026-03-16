# spec-compliance-review Specification

## Purpose
TBD - created by archiving change spec-compliance-review. Update Purpose after archive.
## Requirements
### Requirement: Spec-compliance reviewer dispatched alongside other review agents
The harness SHALL dispatch a `spec-compliance-reviewer` agent as part of the review stage when a change name is available (not in prompt mode).

#### Scenario: Change mode includes spec-compliance review
- **WHEN** the pipeline runs with `--change add-logging` and review is not skipped
- **THEN** the review dispatch SHALL include `spec-compliance-reviewer` alongside bug-hunter, test-reviewer, and quality-reviewer

#### Scenario: Prompt mode skips spec-compliance review
- **WHEN** the pipeline runs with `--prompt "fix bug"`
- **THEN** the review dispatch SHALL NOT include `spec-compliance-reviewer` (no tasks.md to check)

### Requirement: Agent verifies each completed task against the diff
The spec-compliance-reviewer SHALL read tasks.md, identify all `[x]` tasks, and verify each one has corresponding evidence in the git diff.

#### Scenario: Task correctly implemented
- **WHEN** task says "call match_findings with the round's findings" and the diff shows `match_findings(prior_findings, current_findings)` in pipeline.py
- **THEN** no finding SHALL be reported for that task

#### Scenario: Task marked complete but function never called
- **WHEN** task says "call match_findings with the round's findings" but the diff shows match_findings is defined and tested but never called in pipeline.py
- **THEN** a finding SHALL be reported with severity `critical`, file `pipeline.py`, and description indicating the function is implemented but not integrated

#### Scenario: Task describes specific parameters but implementation uses different types
- **WHEN** task says "accept tolerance as Literal['low','med','high']" but the diff shows `tolerance: str`
- **THEN** a finding SHALL be reported with severity `medium` indicating the type mismatch

### Requirement: Agent receives tasks.md and change context
The spec-compliance-reviewer prompt SHALL include the tasks.md content, the git diff, and optionally the proposal and spec files for additional context.

#### Scenario: Agent prompt contains tasks content
- **WHEN** the spec-compliance-reviewer is dispatched
- **THEN** its prompt SHALL contain the full tasks.md content as extra context. The agent fetches the diff itself via `gh pr diff` (same as other review agents).

#### Scenario: No checked tasks produces no findings
- **WHEN** tasks.md contains only unchecked `[ ]` tasks
- **THEN** the agent SHALL report no compliance findings (nothing to verify)

### Requirement: Findings use standard ReviewFinding model
The spec-compliance-reviewer SHALL output findings in the same JSON format as other review agents, using the ReviewFinding model.

#### Scenario: Finding structure
- **WHEN** the agent finds a compliance issue
- **THEN** the finding SHALL have `title`, `file`, `severity`, `description`, and `agent` set to `"spec-compliance-reviewer"`

