# auto-merge Specification

## Purpose
TBD - created by archiving change auto-merge. Update Purpose after archive.
## Requirements
### Requirement: --auto-merge flag enables automatic PR merging
The `harness run` command SHALL accept an `--auto-merge` flag (default off). When enabled and all gates pass, the pipeline SHALL merge the PR after the openspec-review stage.

#### Scenario: Auto-merge enabled, all gates pass
- **WHEN** `--auto-merge` is enabled, eval passed, no protected files touched, no remaining review findings, and openspec-review passed
- **THEN** the pipeline SHALL merge the PR via `gh pr merge <url> --merge --delete-branch`

#### Scenario: Auto-merge not enabled
- **WHEN** `--auto-merge` is not provided
- **THEN** the pipeline SHALL NOT attempt to merge the PR (current behavior)

#### Scenario: Auto-merge in dry-run
- **WHEN** `--auto-merge` is enabled with `--dry-run`
- **THEN** the dry-run plan SHALL show "auto-merge: enabled" but no merge SHALL be attempted

### Requirement: Protected files block auto-merge
When the PR touches protected files (as detected by the protected-paths check), auto-merge SHALL be blocked regardless of other gate results.

#### Scenario: Protected files touched
- **WHEN** `--auto-merge` is enabled and the PR touches files matching `.harness/protected-paths.yml` patterns
- **THEN** the pipeline SHALL NOT merge the PR and SHALL post a comment explaining the block

#### Scenario: No protected paths config
- **WHEN** `--auto-merge` is enabled and no `.harness/protected-paths.yml` exists
- **THEN** the protected-files gate SHALL pass (no files are protected)

### Requirement: Review findings block auto-merge
When review findings remain after all fix-retry rounds, auto-merge SHALL be blocked.

#### Scenario: Findings remain after fix-retry
- **WHEN** `--auto-merge` is enabled and `findings_remain` is True after the review loop
- **THEN** the pipeline SHALL NOT merge the PR

#### Scenario: Review skipped
- **WHEN** `--auto-merge` is enabled and `--skip-review` was also provided
- **THEN** the review gate SHALL pass (operator explicitly skipped review)

#### Scenario: All findings resolved
- **WHEN** review agents found issues but fix-retry resolved all of them
- **THEN** the review gate SHALL pass

### Requirement: OpenSpec review failure blocks auto-merge
When the openspec-review stage fails (validation errors, unresolved findings), auto-merge SHALL be blocked.

#### Scenario: OpenSpec review failed
- **WHEN** `--auto-merge` is enabled and openspec-review returned `success=False`
- **THEN** the pipeline SHALL NOT merge the PR

#### Scenario: OpenSpec review passed
- **WHEN** openspec-review returned `success=True`
- **THEN** the openspec-review gate SHALL pass

#### Scenario: OpenSpec review skipped (prompt mode)
- **WHEN** the pipeline ran in prompt mode (no change name) and openspec-review was skipped
- **THEN** the openspec-review gate SHALL pass

### Requirement: Merge blocked comment posted on PR
When auto-merge is enabled but blocked, the harness SHALL post a PR comment listing which gates passed and which blocked.

#### Scenario: Merge blocked with checklist
- **WHEN** auto-merge is blocked by protected files
- **THEN** the PR comment SHALL include a checklist showing each gate's pass/fail status and the specific reason for the block

### Requirement: Optional CI wait before merge
When `--wait-for-ci` is provided alongside `--auto-merge`, the harness SHALL wait for CI status checks to pass before merging.

#### Scenario: CI passes
- **WHEN** `--auto-merge --wait-for-ci` is enabled and `gh pr checks --watch` reports all checks passed
- **THEN** the pipeline SHALL proceed to merge

#### Scenario: CI fails
- **WHEN** `--auto-merge --wait-for-ci` is enabled and CI checks fail
- **THEN** the pipeline SHALL NOT merge and SHALL log the CI failure

#### Scenario: CI wait not requested
- **WHEN** `--auto-merge` is enabled without `--wait-for-ci`
- **THEN** the pipeline SHALL merge immediately after its own gates pass (no CI wait)

#### Scenario: CI wait timeout
- **WHEN** `--wait-for-ci` is enabled and CI checks do not complete within 10 minutes
- **THEN** the pipeline SHALL NOT merge and SHALL log a timeout warning

#### Scenario: --wait-for-ci without --auto-merge
- **WHEN** `--wait-for-ci` is provided without `--auto-merge`
- **THEN** the CLI SHALL exit with an error: "`--wait-for-ci` requires `--auto-merge`"

### Requirement: MergeResult stage model
The merge stage SHALL produce a `MergeResult` model appended to the pipeline stages list.

#### Scenario: Successful merge
- **WHEN** the PR is merged successfully
- **THEN** `MergeResult` SHALL have `success=True`, `merged=True`, `merge_blocked_reason=None`

#### Scenario: Merge blocked
- **WHEN** auto-merge is blocked by a gate
- **THEN** `MergeResult` SHALL have `success=True` (pipeline didn't fail), `merged=False`, `merge_blocked_reason` set to the reason

#### Scenario: Merge command fails
- **WHEN** `gh pr merge` returns a non-zero exit code
- **THEN** `MergeResult` SHALL have `success=False`, `merged=False`, `error` set to the gh error message

#### Scenario: MergeResult in manifest
- **WHEN** a pipeline run with `--auto-merge` completes and the PR was merged
- **THEN** the `RunManifest.stages` list SHALL contain a `MergeResult` entry with `merged=True`, `merge_blocked_reason=None`, and `type(entry) is MergeResult`

