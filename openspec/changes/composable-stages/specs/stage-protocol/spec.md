## ADDED Requirements

### Requirement: Stage protocol defines uniform interface
All pipeline stages SHALL implement the `Stage` protocol with a `name: str` attribute, a `composite: bool` attribute, and a `run(context: FlowContext) -> StageResult` method. Config is accepted via the stage's constructor, not via `run()`.

#### Scenario: Stage satisfies protocol structurally
- **WHEN** a class has `name: str`, `composite: bool` attributes and a `run(context: FlowContext) -> StageResult` method
- **THEN** it satisfies the `Stage` protocol without inheriting from any base class

#### Scenario: Simple stage returns typed result
- **WHEN** a non-composite stage's `run()` method completes
- **THEN** it returns one of the existing `StageResult` subtypes (`WorktreeResult`, `PrResult`, `ReviewResult`, `OpenSpecReviewResult`, `MergeResult`)
- **THEN** the runner appends the result to `context.stages`

#### Scenario: Composite stage manages its own results
- **WHEN** a composite stage's `run()` method executes (e.g., `WorkerEvalLoopStage`)
- **THEN** it appends intermediate results (`WorkerResult`, `EvalResult` per attempt) to `context.stages` directly
- **THEN** the runner does NOT append the composite stage's return value to `context.stages`

### Requirement: FlowContext carries all shared pipeline state
A `FlowContext` dataclass SHALL carry all inputs, configuration, and mutable state needed by pipeline stages, replacing the 20+ parameter threading in `_run_pipeline_inner`.

#### Scenario: FlowContext provides repo and change info
- **WHEN** a stage reads from FlowContext
- **THEN** it has access to `repo`, `change_name`, `run_id`, `prompt`, `issue_number`, and `profile`

#### Scenario: FlowContext provides CLI config
- **WHEN** a stage reads from FlowContext
- **THEN** it has access to all CLI flags: `max_retries`, `max_turns`, `model`, `effort`, `max_budget_usd`, `permission_mode`, `verbose`, `skip_review`, `auto_merge`, `wait_for_ci`, `review_cycle`, `max_findings_per_retry`

#### Scenario: Stages write mutable state to FlowContext
- **WHEN** a stage completes and needs to pass data to later stages
- **THEN** it writes to FlowContext mutable fields (`worktree_path`, `branch`, `pr_url`, `session_id`, `protected_files`, `baseline_eval`)

#### Scenario: FlowContext accumulates stage results
- **WHEN** a stage completes
- **THEN** its `StageResult` is appended to `context.stages`

### Requirement: Stage config is constructor-injected via per-stage TypedDicts
Each stage SHALL define its own `TypedDict` for configuration. Config is passed at construction time (`__init__`), not at `run()` time. Stages with no config accept no constructor arguments (or an empty TypedDict).

#### Scenario: Stage constructed with typed config
- **WHEN** a `WorkerEvalLoopStage` is constructed with `WorkerEvalLoopConfig(max_retries=1)`
- **THEN** the config is bound to the instance and used during `run()`

#### Scenario: Stages with no config use FlowContext defaults
- **WHEN** a `WorktreeStage` is constructed with no config
- **THEN** it reads all needed values from `FlowContext` during `run()`

### Requirement: Stage registry maps names to implementations
A module-level registry SHALL map stage name strings to stage classes. A `register_stage()` function SHALL add entries. A `get_stage()` function SHALL retrieve them.

#### Scenario: All built-in stages registered at import time
- **WHEN** the stages module is imported
- **THEN** all built-in stages (worktree, worker-eval-loop, create-pr, protected-paths, review-agents, openspec-review, merge-gate) are registered

#### Scenario: Unknown stage name raises error
- **WHEN** `get_stage()` is called with an unregistered name
- **THEN** it raises a `ValueError` with the unknown name and available stage names

### Requirement: Checkpoint-resume works with stage lists
The checkpoint system SHALL store the name of the last completed stage. On resume, the runner SHALL skip stages up to and including the checkpointed stage in the ordered stage list.

#### Scenario: Resume skips completed stages
- **WHEN** a pipeline resumes with a checkpoint that completed "create-pr"
- **THEN** stages before and including "create-pr" in the list are skipped
- **THEN** the next stage after "create-pr" executes

#### Scenario: Checkpoint format updated to use str
- **WHEN** a checkpoint is written by the new stage-based pipeline
- **THEN** `PipelineCheckpoint.completed_stage` is a `str` (not a Literal) containing a valid stage name from the registry

#### Scenario: Old checkpoint names mapped to new names
- **WHEN** a checkpoint from the old pipeline has `completed_stage: "worker_eval"`
- **THEN** the runner maps it to `"worker-eval-loop"` via a compatibility dict
- **THEN** the pipeline resumes correctly from the mapped stage
