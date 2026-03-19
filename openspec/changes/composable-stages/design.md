## Context

`_run_pipeline_inner()` in `pipeline.py` is ~1300 lines with 20+ parameters. Each stage (worktree creation, worker dispatch, eval, PR creation, review agents, openspec review, merge gate) is inlined as a block of code. The function passes state between stages via local variables. Checkpoint-resume uses a `_should_run_stage()` helper that checks stage names against a hardcoded order.

The stage logic itself is already largely modular — each stage calls functions in dedicated modules (`worktree.py`, `worker.py`, `evaluator.py`, `pr.py`, `review_agents.py`, `merge.py`). What's monolithic is the *wiring*: parameter threading, result passing, checkpoint management, and event logging.

## Goals / Non-Goals

**Goals:**
- Define a `Stage` protocol that all pipeline stages implement
- Create a `FlowContext` that replaces the 20+ parameter threading with a single shared state object
- Extract each inline stage block into a Stage class
- Build a stage registry mapping names to implementations
- Refactor `_run_pipeline_inner()` to iterate over a list of stages
- Preserve identical CLI behavior — this is a pure refactor
- Preserve checkpoint-resume semantics

**Non-Goals:**
- YAML flow templates (that's `flow-templates` change)
- Hook system on stages (that's `stage-hooks` change)
- New stages (checkout-pr, merge-branches)
- Agentic orchestration
- Parallel stage execution
- Any CLI changes or new flags

## Decisions

### Stage protocol uses Python Protocol, not ABC

**Decision:** Use `typing.Protocol` for the stage interface, not `abc.ABC`.

**Rationale:** Protocol enables structural subtyping — any class with a matching `run()` method satisfies the interface without inheriting from a base class. This keeps stage implementations decoupled and testable. ABCs would force inheritance chains that add coupling without value.

**Interface:**
```python
class Stage(Protocol):
    name: str

    def run(self, context: FlowContext) -> StageResult: ...
```

Config is passed at construction time, not per-call. Each stage's `__init__` accepts its typed config. The Protocol's `run()` method takes only FlowContext — config is already bound to `self`. This avoids threading a generic `StageConfig` type through the Protocol signature (which would require `Any` or complex generics) and keeps stage construction type-safe.

### FlowContext is a mutable dataclass, not immutable

**Decision:** `FlowContext` is a mutable dataclass that stages read from and write to.

**Rationale:** Stages need to record results that later stages consume (e.g., worktree stage sets `worktree_path`, PR stage reads it). An immutable approach would require each stage to return a new context, adding ceremony without benefit since stages run sequentially. The context is the shared state bus.

**Key fields:**
```python
@dataclass
class FlowContext:
    # Inputs (set at pipeline start)
    repo: Path
    change_name: str
    run_id: str
    prompt: str | None
    issue_number: int | None
    profile: RepoProfile
    event_logger: EventLogger

    # CLI config
    max_retries: int
    max_turns: int
    model: str | None
    effort: str | None
    max_budget_usd: float | None
    permission_mode: str
    verbose: bool
    skip_review: bool
    auto_merge: bool
    wait_for_ci: bool
    review_cycle: list[str]
    max_findings_per_retry: int
    ecosystem: str
    harness_home: Path | None
    repo_name: str | None

    # Mutable state (stages write these)
    worktree_path: Path | None = None
    branch: str | None = None
    pr_url: str | None = None
    session_id: str | None = None
    last_worker_result: WorkerResult | None = None
    last_eval_result: EvalResult | None = None
    protected_files: list[str] = field(default_factory=list)
    baseline_eval: dict[str, bool] = field(default_factory=dict)
    stages: list[StageResultUnion] = field(default_factory=list)
```

**Alternative considered:** Separate `FlowConfig` (immutable inputs) from `FlowState` (mutable results). Rejected as premature — the distinction is clear from field grouping and can be split later if needed.

### Config is constructor-injected, not passed per-call

**Decision:** Each stage accepts its config via `__init__`. Per-stage TypedDicts define the shape. The `run()` method only receives `FlowContext`.

**Rationale:** Putting config in the Protocol's `run()` signature would require either `Any` (banned) or complex generics. Constructor injection keeps each stage type-safe: `WorkerEvalLoopStage(config)` is checked at construction, and `run(context)` is a clean uniform interface. TypedDicts remain serializable for future YAML integration.

```python
class WorkerEvalLoopConfig(TypedDict, total=False):
    max_retries: int  # overrides FlowContext.max_retries if set

class ReviewAgentsConfig(TypedDict, total=False):
    agents: list[str]
    tolerance_sequence: list[str]

# Usage:
stage = WorkerEvalLoopStage(WorkerEvalLoopConfig(max_retries=1))
stage.run(context)  # config already bound
```

### Stage registry is a simple dict, not a plugin system

**Decision:** A module-level `STAGE_REGISTRY: dict[str, type[Stage]]` that maps names to stage classes. Registration via a `register_stage()` function.

**Rationale:** A plugin/entry-point system is overkill for a project where all stages ship in the same package. A dict is discoverable, debuggable, and sufficient. If third-party stages become needed, entry points can wrap this dict later.

### Checkpoint-resume maps to stage names in the list

**Decision:** Checkpoint stores the name of the last completed stage. On resume, the runner skips stages up to and including the checkpointed one.

**Rationale:** This is functionally identical to the current `_should_run_stage()` approach but generalized — it works with any ordered list of stages, not just the hardcoded `_STAGE_ORDER`.

**Breaking change:** `PipelineCheckpoint.completed_stage` must be widened from `Literal["worktree", "worker_eval", "pr", "review", "openspec_review"]` to `str` to support arbitrary stage names from the registry. Old checkpoint files with underscore-based names (e.g., `worker_eval`) will be mapped to the new hyphenated names (e.g., `worker-eval-loop`) via a compatibility dict during the transition. The `MacroStage` type alias is removed.

### worker-eval-loop stays as one composite stage

**Decision:** The worker dispatch + eval + retry loop remains a single `WorkerEvalLoopStage` that manages its own internal loop.

**Rationale:** The retry logic is tightly coupled — the eval result feeds back into the next worker prompt, session resume decisions depend on context usage, progress files bridge iterations. Decomposing this into separate stages would require the runner to understand retry semantics, which defeats the "deterministic orchestration" principle. The composite stage is the right abstraction boundary.

### The runner appends results; composite stages append their own intermediate results

**Decision:** For simple stages, the runner calls `run()`, receives the `StageResult`, and appends it to `context.stages`. For composite stages like `WorkerEvalLoopStage`, the stage itself appends intermediate results (each `WorkerResult` and `EvalResult` per attempt) to `context.stages` during execution, and the runner does NOT append the composite's return value (which serves only as the success/failure signal).

**Rationale:** The composite stage produces multiple results per run (one per retry attempt). The runner can't know how many results to expect. Having the composite stage own its own result appending keeps the logic co-located. The runner's contract is: simple stages return one result (runner appends), composite stages manage their own results (runner skips appending). A `composite: bool` attribute on the Stage Protocol distinguishes the two.

### ProtectedPathsStage returns a PrResult (reuses existing type)

**Decision:** `ProtectedPathsStage` does not introduce a new result type. It returns a `PrResult` with `success=True` (the stage is advisory — it flags but doesn't block). Protected file information is written to `context.protected_files`.

**Rationale:** Adding a `ProtectedPathsResult` type would require updating the `StageResultUnion` discriminator and all serialization code. The stage's output is a side effect (PR comment + label), not a typed result that later stages consume. Reusing `PrResult` keeps the type union stable.

## Risks / Trade-offs

**[Risk] FlowContext grows unbounded as stages are added** → Keep FlowContext fields minimal. Stages that need to pass data to later stages should use `context.stages` (the result list) rather than adding new FlowContext fields. FlowContext is for *cross-cutting* state, not inter-stage communication.

**[Risk] Refactoring breaks subtle pipeline behavior** → Mitigate with comprehensive tests. Run the full test suite after each stage extraction. The existing pipeline tests serve as integration tests that validate behavior preservation.

**[Risk] Performance regression from abstraction overhead** → Negligible. Stage dispatch is Python function calls; the actual work is subprocess execution (Claude Code, git, gh) which dominates runtime by orders of magnitude.

**[Trade-off] Mutable FlowContext vs. explicit data flow** → Mutable shared state is less pure but dramatically simpler for a sequential pipeline. The stages list provides an audit trail of what happened.
