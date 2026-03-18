## ADDED Requirements

### Requirement: Flow resolution searches repo then bundled
The system SHALL resolve flow names by searching `.harness/flows/<name>.yml` in the target repo first, then bundled flows in the action-harness package. The first match wins.

#### Scenario: Repo flow overrides bundled
- **WHEN** both `.harness/flows/standard.yml` exists in the repo AND a bundled `standard.yml` exists
- **THEN** the repo version is used

#### Scenario: Bundled flow used as fallback
- **WHEN** `.harness/flows/quick.yml` does not exist in the repo
- **THEN** the bundled `quick.yml` is used

#### Scenario: Flow not found
- **WHEN** `--flow custom-flow` is specified and no matching file exists in repo or bundled flows
- **THEN** the system raises an error listing available flows from both locations

### Requirement: Default flow is standard
When `--flow` is not specified, the system SHALL use the `standard` flow template.

#### Scenario: No --flow flag
- **WHEN** `harness run --change my-change` is invoked without `--flow`
- **THEN** the `standard` flow is resolved and executed

### Requirement: CLI --flow flag selects flow
The `harness run` command SHALL accept a `--flow <name>` option that selects which flow template to use.

#### Scenario: Explicit flow selection
- **WHEN** `harness run --flow quick --change my-change` is invoked
- **THEN** the `quick` flow template is resolved and executed

#### Scenario: Flow name in dry-run output
- **WHEN** `--dry-run` is used with `--flow quick`
- **THEN** the dry-run output shows which flow template is being used
