# strict-review-triage Specification

## Purpose
TBD - created by archiving change strict-review-triage. Update Purpose after archive.
## Requirements
### Requirement: Triage triggers fix-retry on any findings
The `triage_findings` function SHALL accept a `tolerance` parameter and return `True` (needs fix) when any findings exist at or above the tolerance threshold. At tolerance `low`, this is equivalent to triggering on any findings. At `med`, only medium/high/critical trigger fix-retry. At `high`, only high/critical trigger fix-retry.

#### Scenario: Tolerance low triggers on any finding
- **WHEN** review agents return findings of any severity and tolerance is `low`
- **THEN** `triage_findings` returns `True`

#### Scenario: Tolerance med ignores low findings
- **WHEN** review agents return only low-severity findings and tolerance is `med`
- **THEN** `triage_findings` returns `False`

#### Scenario: Tolerance high ignores low and medium findings
- **WHEN** review agents return only medium and low findings and tolerance is `high`
- **THEN** `triage_findings` returns `False`

#### Scenario: No findings skips fix-retry at any tolerance
- **WHEN** review agents return 0 findings across all agents
- **THEN** `triage_findings` returns `False` regardless of tolerance level

### Requirement: Quality reviewer grounded in repo conventions
The quality-reviewer system prompt SHALL instruct the agent to read the repo's CLAUDE.md and linter configuration before reviewing. Findings SHALL cite the specific rule or convention being enforced. Findings not grounded in repo rules SHALL NOT be raised.

#### Scenario: Finding cites repo rule
- **WHEN** the quality reviewer finds a convention violation
- **THEN** the finding description references the specific CLAUDE.md rule, linter rule, or existing pattern it violates

### Requirement: Fix-retry feedback includes actionable findings and prior acknowledgments
The `format_review_feedback` function SHALL include only actionable findings (at or above the tolerance threshold) in the feedback sent to the fix-retry worker. The feedback SHALL also include a "Prior Acknowledged Findings" section listing findings from earlier rounds that were acknowledged but not fixed, if any exist.

#### Scenario: Only actionable findings in feedback
- **WHEN** findings include 1 high and 2 low findings and tolerance is `med`
- **THEN** the feedback string contains only the 1 high finding as an actionable item

#### Scenario: Prior acknowledged findings included
- **WHEN** round 1 had a finding that the worker acknowledged but did not fix
- **AND** the pipeline is formatting feedback for round 2
- **THEN** the feedback includes a "Prior Acknowledged Findings" section with that finding

