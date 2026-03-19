## ADDED Requirements

### Requirement: Flow template YAML structure
A flow template SHALL be a YAML file with `name`, `description`, and `stages` fields. An optional `schema_version` field defaults to `1`.

#### Scenario: Minimal valid flow
- **WHEN** a YAML file contains `name`, `description`, and a `stages` list with at least one `stage` entry
- **THEN** it is a valid flow template

#### Scenario: Missing required fields
- **WHEN** a YAML file is missing `name` or `stages`
- **THEN** parsing raises a validation error with the missing field name

#### Scenario: YAML parsed safely
- **WHEN** a flow template file is loaded
- **THEN** the parser uses `yaml.safe_load()` exclusively (never `yaml.load()` or `yaml.unsafe_load()`)

### Requirement: Stage entries reference registered stages
Each `stage` entry in the stages list SHALL reference a stage name from the stage registry. An optional `config` dict provides per-stage typed configuration. An optional `when` field specifies a named predicate for conditional execution.

#### Scenario: Stage with config
- **WHEN** a stage entry has `stage: worker-eval-loop` and `config: {max_retries: 1}`
- **THEN** the runner constructs the stage with the config dict (constructor injection) before calling `run()`

#### Scenario: Stage with condition
- **WHEN** a stage entry has `when: auto_merge`
- **THEN** the runner evaluates the `auto_merge` predicate against FlowContext before executing

#### Scenario: Unknown stage name
- **WHEN** a stage entry references a name not in the stage registry
- **THEN** parsing raises a validation error listing available stages

### Requirement: Parallel blocks for concurrent stage execution
A `parallel` entry in the stages list SHALL contain a list of stage entries that execute concurrently. All stages in a parallel block MUST complete before the next entry in the flow executes.

#### Scenario: Parallel execution
- **WHEN** a parallel block contains `protected-paths` and `review-agents`
- **THEN** both stages execute concurrently and the flow waits for both to complete

#### Scenario: Parallel stage failure
- **WHEN** any stage in a parallel block fails
- **THEN** the remaining parallel stages are allowed to complete, and the overall block reports failure

#### Scenario: Parallel block output field overlap rejected
- **WHEN** two stages in a parallel block both declare the same FlowContext field in their `output_fields`
- **THEN** flow parsing raises a validation error naming the conflicting stages and the overlapping field

### Requirement: Named predicates for conditional execution
The system SHALL support named predicates: `is_openspec_change`, `auto_merge`, `has_pr`. Predicates are evaluated against FlowContext. Unknown predicate names SHALL raise a validation error at parse time.

#### Scenario: Predicate evaluates to false
- **WHEN** a stage has `when: auto_merge` and `context.auto_merge` is False
- **THEN** the stage is skipped and the runner proceeds to the next entry

#### Scenario: Unknown predicate
- **WHEN** a stage has `when: nonexistent_predicate`
- **THEN** flow parsing raises a validation error listing available predicates
