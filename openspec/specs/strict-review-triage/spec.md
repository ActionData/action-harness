# strict-review-triage Specification

## Purpose
TBD - created by archiving change strict-review-triage. Update Purpose after archive.
## Requirements
### Requirement: Triage triggers fix-retry on any findings
The `triage_findings` function SHALL return `True` (needs fix) when ANY findings exist, regardless of severity.

#### Scenario: Medium finding triggers fix-retry
- **WHEN** review agents return 1 medium finding and 0 high/critical findings
- **THEN** `triage_findings` returns `True` and the worker is re-dispatched to address it

#### Scenario: Low finding triggers fix-retry
- **WHEN** review agents return 2 low findings and 0 medium/high/critical findings
- **THEN** `triage_findings` returns `True` and the worker is re-dispatched

#### Scenario: No findings skips fix-retry
- **WHEN** review agents return 0 findings across all agents
- **THEN** `triage_findings` returns `False` and the pipeline proceeds without fix-retry

### Requirement: Fix-retry feedback includes all findings
The `format_review_feedback` function SHALL include ALL findings in the feedback string sent to the fix-retry worker. Each finding SHALL include severity, file, line, and description.

#### Scenario: All severities in feedback
- **WHEN** findings include 1 high, 1 medium, and 2 low findings
- **THEN** the feedback string contains all 4 findings with their details and the footer reads "Fix the issues above"

### Requirement: Quality reviewer grounded in repo conventions
The quality-reviewer system prompt SHALL instruct the agent to read the repo's CLAUDE.md and linter configuration before reviewing. Findings SHALL cite the specific rule or convention being enforced. Findings not grounded in repo rules SHALL NOT be raised.

#### Scenario: Finding cites repo rule
- **WHEN** the quality reviewer finds a convention violation
- **THEN** the finding description references the specific CLAUDE.md rule, linter rule, or existing pattern it violates

### Requirement: Review-fix loop capped at 2 rounds
The pipeline SHALL run a review-fix loop: dispatch review agents, triage, fix-retry if needed, then re-dispatch review agents to verify. This loop SHALL run up to 2 times. After 2 rounds, remaining findings are posted as a PR comment and the pipeline continues.

#### Scenario: First round fixes all findings
- **WHEN** the worker addresses all findings and re-review finds no issues
- **THEN** the pipeline proceeds after 1 round

#### Scenario: Re-review after fix-retry
- **WHEN** the first fix-retry round completes
- **THEN** review agents are re-dispatched to check if findings were addressed

#### Scenario: Second round needed
- **WHEN** re-review after the first fix-retry finds remaining issues
- **THEN** a second fix-retry round is dispatched with the remaining findings

#### Scenario: Findings remain after 2 rounds
- **WHEN** findings still remain after 2 complete review-fix rounds
- **THEN** the pipeline posts remaining findings as a PR comment noting "Remaining findings after 2 fix-retry rounds" and continues without further retries

