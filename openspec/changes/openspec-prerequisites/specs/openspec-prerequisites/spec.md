## ADDED Requirements

### Requirement: Prerequisites field in .openspec.yaml
Changes MAY have a `prerequisites` field in `.openspec.yaml` listing change names that must be completed before implementation.

#### Scenario: Change with prerequisites
- **WHEN** `.openspec.yaml` contains `prerequisites: [repo-lead, always-on]`
- **THEN** the prerequisites SHALL be parsed as a list of change name strings

#### Scenario: Change without prerequisites
- **WHEN** `.openspec.yaml` has no `prerequisites` field
- **THEN** the change SHALL be treated as having no dependencies (always ready)

### Requirement: Ready command lists unblocked changes
The `harness ready --repo <path>` command SHALL list all active changes whose prerequisites are fully satisfied.

#### Scenario: All prerequisites met
- **WHEN** change `merge-queue` has prerequisites `[repo-lead]` and `repo-lead` is archived
- **THEN** `merge-queue` SHALL appear in the ready list

#### Scenario: Prerequisites not met
- **WHEN** change `merge-queue` has prerequisites `[always-on]` and `always-on` is still active
- **THEN** `merge-queue` SHALL appear in the blocked list with the unmet prerequisite shown

#### Scenario: No active changes
- **WHEN** the repo has no active changes in `openspec/changes/`
- **THEN** the command SHALL output "No active changes found"

### Requirement: Prerequisite satisfaction check
A prerequisite is satisfied when the named change has been archived (exists in `openspec/changes/archive/`) OR has a main spec (exists at `openspec/specs/<name>/`).

#### Scenario: Archived prerequisite
- **WHEN** prerequisite `repo-lead` has an archive at `openspec/changes/archive/*-repo-lead/`
- **THEN** the prerequisite SHALL be considered satisfied

#### Scenario: Main spec exists
- **WHEN** prerequisite `repo-lead` has a spec at `openspec/specs/repo-lead/`
- **THEN** the prerequisite SHALL be considered satisfied

#### Scenario: Unknown prerequisite
- **WHEN** a prerequisite name does not match any known change (active, archived, or spec'd)
- **THEN** the command SHALL log a warning about the unknown prerequisite and treat it as unmet

### Requirement: JSON output
The `--json` flag SHALL output the readiness data as JSON.

#### Scenario: JSON output
- **WHEN** `harness ready --repo . --json` is run
- **THEN** stdout SHALL contain JSON with keys `ready` (list of change names) and `blocked` (list of objects with `name` and `unmet_prerequisites`)

### Requirement: Lead context integration
The `gather_lead_context` function SHALL include ready changes in the lead's context.

#### Scenario: Lead sees ready changes
- **WHEN** the lead is dispatched and there are ready changes
- **THEN** the lead's context SHALL include a "Ready Changes" section listing them
