## MODIFIED Requirements

### Requirement: Stage entries reference registered stages
Each `stage` entry in the stages list SHALL reference a stage name from the stage registry. An optional `config` dict provides per-stage typed configuration. An optional `when` field specifies a named predicate for conditional execution. An optional `hooks` dict maps lifecycle event names (`after_attempt`, `before_redispatch`, `on_success`, `on_failure`) to hook registry names. Phase 1 supports one hook per event (not a list).

#### Scenario: Stage with config
- **WHEN** a stage entry has `stage: worker-eval-loop` and `config: {max_retries: 1}`
- **THEN** the runner constructs the stage with the config dict (constructor injection) before calling `run()`

#### Scenario: Stage with condition
- **WHEN** a stage entry has `when: auto_merge`
- **THEN** the runner evaluates the `auto_merge` predicate against FlowContext before executing

#### Scenario: Unknown stage name
- **WHEN** a stage entry references a name not in the stage registry
- **THEN** parsing raises a validation error listing available stages

#### Scenario: Stage with hooks
- **WHEN** a stage entry has `hooks: {after_attempt: openspec-update-tasks}`
- **THEN** the flow parser resolves the hook name from the hook registry and passes the hook instance to the stage constructor

#### Scenario: Unknown hook name in stage entry
- **WHEN** a stage entry references a hook name not in the hook registry
- **THEN** flow parsing raises a validation error listing available hooks

#### Scenario: Multiple hooks per event rejected
- **WHEN** a stage entry has `hooks: {after_attempt: [hook-a, hook-b]}`
- **THEN** flow parsing raises a validation error stating only one hook per event is supported in phase 1
