## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Fix-retry feedback includes actionable findings and prior acknowledgments
The `format_review_feedback` function SHALL include only actionable findings (at or above the tolerance threshold) in the feedback sent to the fix-retry worker. The feedback SHALL also include a "Prior Acknowledged Findings" section listing findings from earlier rounds that were acknowledged but not fixed, if any exist.

#### Scenario: Only actionable findings in feedback
- **WHEN** findings include 1 high and 2 low findings and tolerance is `med`
- **THEN** the feedback string contains only the 1 high finding as an actionable item

#### Scenario: Prior acknowledged findings included
- **WHEN** round 1 had a finding that the worker acknowledged but did not fix
- **AND** the pipeline is formatting feedback for round 2
- **THEN** the feedback includes a "Prior Acknowledged Findings" section with that finding

## REMOVED Requirements

### Requirement: Fix-retry feedback includes all findings
**Reason**: Replaced by tolerance-aware feedback. The new "Fix-retry feedback includes actionable findings and prior acknowledgments" requirement filters findings by tolerance and adds prior acknowledged findings section.

### Requirement: Review-fix loop capped at 2 rounds
**Reason**: Replaced by configurable review cycle. The number and tolerance of review rounds is now defined by the `--review-cycle` flag (default: `["low", "med", "high"]`).
**Migration**: Use `--review-cycle low,low` to replicate the previous 2-round behavior with all-severity triage.
