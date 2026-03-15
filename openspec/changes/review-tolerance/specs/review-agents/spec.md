## MODIFIED Requirements

### Requirement: Severity-Based Triage

After all agents complete, the pipeline SHALL filter findings by the current round's tolerance level. Findings with severity rank at or above the tolerance threshold are actionable. If any actionable findings exist, the pipeline SHALL re-dispatch the code worker with only the actionable findings as structured feedback. Non-actionable findings SHALL still be posted to the PR comment for visibility.

#### Scenario: Tolerance filters actionable findings
- **WHEN** review agents produce findings and the current tolerance is `med`
- **THEN** `triage_findings` considers only medium, high, and critical findings when deciding whether to trigger fix-retry
- **AND** low-severity findings are excluded from the fix-retry feedback

#### Scenario: All findings posted to PR regardless of tolerance
- **WHEN** review agents produce findings at any severity
- **THEN** the PR comment includes all findings regardless of the current tolerance level

#### Scenario: No actionable findings at current tolerance
- **WHEN** all review findings have severity below the current tolerance threshold
- **THEN** the pipeline does not re-dispatch the worker
- **AND** findings are posted to the PR comment

### Requirement: Configurable Review Loop

The review-fix loop SHALL iterate through the configured review cycle (an ordered list of tolerance levels) rather than a hardcoded number of rounds. Each round dispatches review agents, triages at that round's tolerance, and runs fix-retry if actionable findings exist. The loop terminates when the cycle is exhausted or a round produces zero actionable findings.

#### Scenario: Cycle defines number of rounds
- **WHEN** the review cycle is `["low", "med", "high"]`
- **THEN** the pipeline runs up to 3 review rounds, one per cycle element

#### Scenario: Short-circuit on clean round
- **WHEN** a review round produces zero actionable findings
- **THEN** remaining rounds in the cycle are skipped

#### Scenario: Fix retry fails eval
- **WHEN** the fix worker completes but eval fails
- **THEN** the pipeline records the failure and stops the review loop

