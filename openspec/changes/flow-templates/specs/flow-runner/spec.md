## ADDED Requirements

### Requirement: Deterministic flow runner executes parsed templates
The flow runner SHALL accept a parsed flow template and a FlowContext, then execute stages in order. It handles sequential stages, parallel blocks, and conditional skipping.

#### Scenario: Sequential execution
- **WHEN** a flow has stages [worktree, worker-eval-loop, create-pr]
- **THEN** the runner executes them in order, passing FlowContext to each

#### Scenario: Simple stage result appended by runner
- **WHEN** a non-composite stage returns a `StageResult`
- **THEN** the runner appends it to `context.stages`

#### Scenario: Composite stage manages its own results
- **WHEN** a composite stage (`stage.composite == True`) returns
- **THEN** the runner does NOT append the return value (the stage already appended intermediate results)

#### Scenario: Stage failure stops pipeline
- **WHEN** a stage returns `success=False`
- **THEN** the runner stops execution, skips remaining stages, and returns the failure

#### Scenario: Conditional stage skipped
- **WHEN** a stage has `when: auto_merge` and the predicate is False
- **THEN** the stage is skipped and the runner continues to the next entry

#### Scenario: Parallel block execution
- **WHEN** the runner encounters a `parallel` block
- **THEN** it dispatches all contained stages concurrently using ThreadPoolExecutor and waits for all to complete

### Requirement: Checkpoint integration with flow runner
The flow runner SHALL write checkpoints after each completed stage and skip already-checkpointed stages on resume.

#### Scenario: Checkpoint written per stage
- **WHEN** a stage completes successfully
- **THEN** the runner writes a checkpoint with that stage's name

#### Scenario: Resume skips completed stages
- **WHEN** the runner starts with a checkpoint indicating "create-pr" is complete
- **THEN** stages up to and including "create-pr" are skipped

### Requirement: Event logging for flow execution
The flow runner SHALL emit events for flow start, each stage entry/exit, conditional skips, parallel block start/end, and flow completion.

#### Scenario: Stage entry/exit events
- **WHEN** a stage starts and completes
- **THEN** the runner emits `stage.started` and `stage.completed` events with the stage name and duration
