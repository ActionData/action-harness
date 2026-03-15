## ADDED Requirements

### Requirement: Tolerance Levels

The pipeline SHALL support three tolerance levels that control which finding severities are actionable: `low` (all severities), `med` (medium, high, critical), `high` (high, critical only). Severity ranking SHALL be: low=0, medium=1, high=2, critical=3. A finding is actionable at a given tolerance when its severity rank is greater than or equal to the tolerance threshold (low=0, med=1, high=2).

#### Scenario: Tolerance low includes all severities
- **WHEN** tolerance is `low`
- **THEN** findings with severity low, medium, high, and critical are all actionable

#### Scenario: Tolerance med excludes low
- **WHEN** tolerance is `med`
- **THEN** findings with severity medium, high, and critical are actionable
- **AND** findings with severity low are not actionable

#### Scenario: Tolerance high excludes low and medium
- **WHEN** tolerance is `high`
- **THEN** findings with severity high and critical are actionable
- **AND** findings with severity low and medium are not actionable

### Requirement: Configurable Review Cycle

The pipeline SHALL accept a review cycle as an ordered list of tolerance levels. Each element defines one review round at that tolerance. The default cycle SHALL be `["low", "med", "high"]`. The cycle SHALL be configurable via the `--review-cycle` CLI flag as a comma-separated string (e.g., `low,med,high`).

#### Scenario: Default review cycle
- **WHEN** no `--review-cycle` flag is provided
- **THEN** the pipeline uses the cycle `["low", "med", "high"]`

#### Scenario: Custom single-round cycle
- **WHEN** `--review-cycle high` is provided
- **THEN** the pipeline runs exactly one review round at tolerance `high`

#### Scenario: Custom multi-round cycle
- **WHEN** `--review-cycle low,low,med` is provided
- **THEN** the pipeline runs up to three review rounds: first at `low`, second at `low`, third at `med`

#### Scenario: Invalid tolerance value rejected
- **WHEN** `--review-cycle foo` is provided
- **THEN** the CLI exits with an error indicating valid values are `low`, `med`, `high`

### Requirement: Tolerance-Based Triage

After each review round, the pipeline SHALL filter findings by the current round's tolerance level. Only actionable findings (at or above the tolerance threshold) SHALL be sent to the fix-retry worker. All findings regardless of severity SHALL be posted to the PR comment for visibility.

#### Scenario: Low findings excluded at med tolerance
- **WHEN** review agents produce 2 low and 1 high finding and the current tolerance is `med`
- **THEN** only the 1 high finding is sent to the fix-retry worker
- **AND** all 3 findings appear in the PR comment

#### Scenario: No actionable findings skips fix-retry
- **WHEN** review agents produce only low findings and the current tolerance is `high`
- **THEN** no fix-retry is dispatched for this round
- **AND** the low findings are posted to the PR comment

### Requirement: Short-Circuit on Clean Review

If a review round produces zero actionable findings after tolerance filtering, the pipeline SHALL skip all remaining rounds in the cycle. A clean round at a given tolerance means subsequent rounds at equal or higher tolerance will also be clean.

#### Scenario: Clean first round skips remaining rounds
- **WHEN** the first round (tolerance `low`) produces zero findings
- **THEN** rounds 2 and 3 are not executed
- **AND** the pipeline proceeds to the next stage

#### Scenario: Clean second round skips remaining rounds
- **WHEN** round 1 produces findings, fix-retry succeeds, and round 2 produces zero actionable findings
- **THEN** round 3 is not executed

### Requirement: Mandatory Finding Acknowledgment

The fix-retry worker SHALL address every actionable finding in the current round. For each finding, the worker SHALL either fix the issue in code or post a PR comment explaining why no code change is needed. The worker's feedback prompt SHALL include explicit instructions for this protocol.

#### Scenario: Worker fixes a finding
- **WHEN** the worker receives an actionable finding
- **AND** the worker determines a code change is appropriate
- **THEN** the worker makes the code change

#### Scenario: Worker declines a finding
- **WHEN** the worker receives an actionable finding
- **AND** the worker determines no code change is needed
- **THEN** the worker posts a PR comment explaining the reasoning

#### Scenario: Worker silently ignores a finding
- **WHEN** the worker receives an actionable finding and neither fixes it nor posts a PR comment
- **THEN** the finding is still treated as acknowledged-but-not-fixed for escalation purposes
- **AND** the finding appears in subsequent round feedback as a prior acknowledged finding

### Requirement: Two-Strike Code Comment Escalation

When a finding with the same file and similar concern appears in two consecutive review rounds without being fixed, the fix-retry worker SHALL add a code comment at the relevant location in addition to the PR comment. The pipeline SHALL track acknowledged-but-not-fixed findings across rounds and include them in subsequent round feedback as "Prior Acknowledged Findings."

#### Scenario: First-time acknowledgment is PR comment only
- **WHEN** the worker acknowledges a finding for the first time (no prior round flagged the same concern)
- **THEN** the worker posts a PR comment only
- **AND** no code comment is required

#### Scenario: Second-time flag escalates to code comment
- **WHEN** a finding in the current round matches a prior acknowledged finding (same file, similar concern)
- **THEN** the worker adds a code comment at the relevant location
- **AND** the worker posts a PR comment

#### Scenario: Prior acknowledged findings included in feedback
- **WHEN** the fix-retry worker is dispatched for round N (N > 1)
- **AND** round N-1 had findings that were acknowledged but not fixed
- **THEN** the feedback prompt includes a "Prior Acknowledged Findings" section listing those findings

### Requirement: Tolerance Recorded in Review Result

Each `ReviewResult` in the run manifest SHALL include the tolerance level used for triage in that round.

#### Scenario: ReviewResult includes tolerance
- **WHEN** a review round completes at tolerance `med`
- **THEN** the `ReviewResult` recorded in the manifest includes `tolerance: "med"`

#### Scenario: ReviewResult tolerance is null when tolerance not applicable
- **WHEN** a `ReviewResult` is created outside the tolerance system (e.g., legacy or skip-review path)
- **THEN** the `tolerance` field is `None`

### Requirement: Verification Review Tolerance

After the final fix-retry in the cycle succeeds, the verification review SHALL filter findings at the same tolerance level as the last round in the cycle.

#### Scenario: Verification uses last round's tolerance
- **WHEN** the review cycle is `["low", "med", "high"]` and the pipeline reaches verification
- **THEN** the verification review filters actionable findings at tolerance `high`

#### Scenario: Verification after single-round cycle
- **WHEN** the review cycle is `["low"]` and fix-retry succeeds
- **THEN** the verification review filters actionable findings at tolerance `low`
