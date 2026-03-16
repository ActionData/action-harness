## ADDED Requirements

### Requirement: Spec-writer agents dispatch in parallel for each gap
When `--propose` is specified, the harness SHALL dispatch a spec-writer agent for each identified gap to generate an OpenSpec change proposal. Dispatches SHALL be parallelizable.

#### Scenario: Multiple gaps generate multiple proposals
- **WHEN** the assessment identifies 3 gaps with `proposal_name` values
- **THEN** the harness SHALL dispatch 3 spec-writer agents (potentially in parallel) and create 3 OpenSpec changes

#### Scenario: Gap without proposal_name is skipped
- **WHEN** a gap has `proposal_name: null`
- **THEN** no spec-writer agent SHALL be dispatched for that gap

### Requirement: Spec-writer agents receive repo context
Each spec-writer agent SHALL receive the gap finding, repo context (ecosystem, existing tools, CLAUDE.md contents), and instructions to create a focused OpenSpec change with at minimum a proposal.md.

#### Scenario: Spec-writer input includes gap details
- **WHEN** a spec-writer agent is dispatched for a gap
- **THEN** its prompt SHALL include the gap severity, finding description, category, and relevant mechanical signals

#### Scenario: Spec-writer input includes repo context
- **WHEN** a spec-writer agent is dispatched
- **THEN** its prompt SHALL include the repo ecosystem, existing tool configuration, and CLAUDE.md contents (if present)

### Requirement: Generated proposals are valid OpenSpec changes
Each generated proposal SHALL be a valid OpenSpec change directory with at minimum a `.openspec.yaml` and `proposal.md`.

#### Scenario: Proposal directory created
- **WHEN** a spec-writer agent completes successfully
- **THEN** `openspec/changes/<proposal_name>/` SHALL exist with `.openspec.yaml` and `proposal.md`

#### Scenario: Spec-writer failure does not block other proposals
- **WHEN** one spec-writer agent fails
- **THEN** other spec-writer agents SHALL continue and their proposals SHALL be created

### Requirement: --propose implies --deep
The `--propose` flag SHALL require `--deep` mode. If `--propose` is provided without `--deep`, the harness SHALL run deep assessment automatically before generating proposals.

#### Scenario: --propose without --deep
- **WHEN** the user runs `harness assess --repo ./path --propose`
- **THEN** the harness SHALL run both mechanical scan and agent assessment before dispatching spec-writers

### Requirement: Report includes proposal generation results
When `--propose` is used, the terminal output SHALL list the generated proposals with their change names and paths.

#### Scenario: Proposals listed in output
- **WHEN** `--propose` generates 2 proposals
- **THEN** the terminal output SHALL list both proposal names and their paths under `openspec/changes/`
