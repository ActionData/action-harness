## ADDED Requirements

### Requirement: StageHook protocol with lifecycle callbacks
The `StageHook` protocol SHALL define four lifecycle methods: `after_attempt`, `before_redispatch`, `on_success`, `on_failure`. A `BaseHook` plain class (NOT inheriting from StageHook) SHALL provide no-op defaults for all methods.

#### Scenario: Hook implements subset of callbacks
- **WHEN** a hook class extends `BaseHook` and overrides only `after_attempt`
- **THEN** the other callbacks are no-ops and the hook satisfies `StageHook` structurally

#### Scenario: after_attempt receives WorkerResult
- **WHEN** `after_attempt` is called after a worker dispatch completes (before eval)
- **THEN** it receives the `FlowContext`, attempt number (int, 1-based), and `WorkerResult`

#### Scenario: before_redispatch receives EvalResult
- **WHEN** `before_redispatch` is called before a retry dispatch (attempts 2+)
- **THEN** it receives the `FlowContext`, attempt number (int), and the `EvalResult` that triggered the retry

#### Scenario: before_redispatch does not fire on first attempt
- **WHEN** the worker-eval loop runs attempt 1
- **THEN** `before_redispatch` is NOT called (there is no prior eval result)
- **THEN** `after_attempt` IS called after the worker completes

#### Scenario: on_success receives final EvalResult
- **WHEN** `on_success` fires after the final successful eval
- **THEN** it receives the `FlowContext` and the passing `EvalResult`

#### Scenario: on_failure receives error context
- **WHEN** `on_failure` fires after retries are exhausted
- **THEN** it receives the `FlowContext`, an error string, and the last `EvalResult` (or `None` if the worker itself failed)

### Requirement: BaseHook is a plain class, not a Protocol subclass
`BaseHook` SHALL be a plain class with concrete no-op implementations. It SHALL NOT inherit from `StageHook`. Hook implementations SHALL inherit from `BaseHook` to get default no-ops and override only the methods they need.

#### Scenario: BaseHook does not inherit from StageHook
- **WHEN** `BaseHook` is defined
- **THEN** its base classes do NOT include `StageHook` (it is a plain `class BaseHook:`, not `class BaseHook(StageHook):`)

### Requirement: Hook registry maps names to implementations
A module-level `HOOK_REGISTRY` SHALL map hook name strings to hook instances. A `register_hook()` function SHALL add entries. A `get_hook()` function SHALL retrieve them.

#### Scenario: Built-in hooks registered at import time
- **WHEN** the hooks module is imported
- **THEN** `openspec-update-tasks` and `openspec-archive` are registered

#### Scenario: Unknown hook name raises error
- **WHEN** `get_hook()` is called with an unregistered name
- **THEN** it raises a `ValueError` with the unknown name and available hook names

### Requirement: Hook failures are advisory and never block the pipeline
All hook invocations SHALL be wrapped in try/except. Failures SHALL be logged to stderr but SHALL NOT stop pipeline execution or affect the stage result.

#### Scenario: Hook raises exception
- **WHEN** a hook's `after_attempt` raises an exception
- **THEN** the exception is logged to stderr and the pipeline continues normally

### Requirement: Hooks SHALL NOT modify pipeline-critical FlowContext fields
Hooks MAY read all FlowContext fields. Hooks SHALL NOT modify fields that affect pipeline control flow: `worktree_path`, `branch`, `pr_url`, `session_id`, `stages`, `baseline_eval`.

#### Scenario: Hook modifying protected field is a contract violation
- **WHEN** a test hook sets `context.pr_url = None`
- **THEN** this is a documented contract violation (not enforced at runtime, but tested as a negative assertion in unit tests)

### Requirement: WorkerEvalLoopStage dispatches hooks at lifecycle points
The `WorkerEvalLoopStage` SHALL call registered hooks at four points in the worker-eval loop.

#### Scenario: Hooks called in retry loop
- **WHEN** worker-eval-loop runs 3 attempts and succeeds on attempt 3
- **THEN** `after_attempt` is called 3 times (after each worker dispatch, before each eval)
- **THEN** `before_redispatch` is called 2 times (before attempts 2 and 3, after failed evals)
- **THEN** `on_success` is called once (after attempt 3's eval passes)

#### Scenario: No hooks configured
- **WHEN** a stage has no hooks in its flow template config
- **THEN** no hook callbacks are invoked and the stage behaves identically to the unhooked version

### Requirement: Flow templates declare hooks via hooks field
Stage entries in flow templates SHALL support an optional `hooks` field mapping lifecycle event names (`after_attempt`, `before_redispatch`, `on_success`, `on_failure`) to hook registry names. Phase 1 supports one hook per event (not a list).

#### Scenario: Hook declared in YAML
- **WHEN** a flow template has `hooks: {after_attempt: openspec-update-tasks}`
- **THEN** the flow parser resolves the hook name from the registry and attaches it to the stage

#### Scenario: Unknown hook name in YAML
- **WHEN** a flow template references a hook name not in the registry
- **THEN** flow parsing raises a validation error

#### Scenario: Multiple hooks per event rejected in phase 1
- **WHEN** a flow template has `hooks: {after_attempt: [hook-a, hook-b]}`
- **THEN** flow parsing raises a validation error stating only one hook per event is supported
