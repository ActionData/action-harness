## ADDED Requirements

### Requirement: Gap detection identifies missing harness infrastructure
The system SHALL detect which harness infrastructure components are missing from a target repo. The checked components are: `openspec/` directory, `HARNESS.md` file, and project registration in harness home. The result SHALL be a structured report listing each component and its status (present or missing).

#### Scenario: Fully onboarded repo
- **WHEN** `detect_gaps()` is called on a repo with `openspec/`, `HARNESS.md`, and a valid `config.yaml` registration
- **THEN** the result SHALL report all components as present and `has_gaps` SHALL be `False`

#### Scenario: Completely un-onboarded repo
- **WHEN** `detect_gaps()` is called on a repo with none of the harness infrastructure
- **THEN** the result SHALL report all components as missing and `has_gaps` SHALL be `True`

#### Scenario: Partially onboarded repo
- **WHEN** `detect_gaps()` is called on a repo with `openspec/` present but `HARNESS.md` missing
- **THEN** the result SHALL report `openspec` as present and `harness_md` as missing

### Requirement: Gap filling scaffolds missing components idempotently
The system SHALL scaffold only the missing components identified by gap detection. Components that already exist SHALL NOT be modified or overwritten. The operation SHALL be safe to run multiple times.

#### Scenario: Scaffold openspec via init
- **WHEN** `fill_gaps()` is called and `openspec/` is missing
- **THEN** the system SHALL run `openspec init --tools claude` as a subprocess in the target repo directory

#### Scenario: Scaffold HARNESS.md with detected eval commands
- **WHEN** `fill_gaps()` is called and `HARNESS.md` is missing
- **THEN** the system SHALL create `HARNESS.md` with eval commands detected by `profile_repo()`, including a comment noting the commands were auto-detected

#### Scenario: Register project in harness home
- **WHEN** `fill_gaps()` is called and the repo has no `config.yaml` in its harness home project directory
- **THEN** the system SHALL call `ensure_project_dir()` and `write_project_config()` to register the project

#### Scenario: Skip existing components
- **WHEN** `fill_gaps()` is called and `openspec/` already exists
- **THEN** the system SHALL NOT run `openspec init` and SHALL report the component as skipped

#### Scenario: openspec CLI not installed
- **WHEN** `fill_gaps()` attempts to run `openspec init` and the CLI is not found
- **THEN** the system SHALL log a clear error message and continue with remaining scaffolding steps

### Requirement: CLI onboard command with confirmation
The `harness onboard --repo <path-or-ref>` command SHALL detect gaps, show what it will do, prompt for confirmation, and then scaffold missing components.

#### Scenario: Onboard a new repo
- **WHEN** the user runs `harness onboard --repo ./my-repo`
- **THEN** the system SHALL display the gap report, prompt for confirmation, and on approval scaffold the missing components

#### Scenario: Onboard with --yes flag
- **WHEN** the user runs `harness onboard --repo ./my-repo --yes`
- **THEN** the system SHALL skip the confirmation prompt and scaffold immediately

#### Scenario: Onboard a fully onboarded repo
- **WHEN** the user runs `harness onboard --repo ./my-repo` and no gaps exist
- **THEN** the system SHALL display a message that the repo is fully onboarded and exit successfully

#### Scenario: Onboard shows summary after completion
- **WHEN** onboarding completes successfully
- **THEN** the system SHALL display a summary of what was created and suggest running `harness lead --repo <path>` to set up the roadmap and priorities
