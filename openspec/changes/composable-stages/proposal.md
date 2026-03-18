## Why

`pipeline.py` is an 1800-line monolith where all 9 stages are wired together in a single function (`_run_pipeline_inner`). Adding a new stage means modifying a massive function with 20+ parameters. Reordering, skipping, or composing stages differently (e.g., a lightweight "quick" flow for small changes) is impossible without forking the function. This blocks the ability to offer multiple flow types (quick, review-only, parallel-modules) and makes the pipeline hard to extend as the harness grows.

## What Changes

- Define a `Stage` protocol with a uniform interface: `run(context: FlowContext) -> StageResult`
- Create a `FlowContext` dataclass that carries all shared state (repo info, prior results, config, event logger)
- Extract each existing pipeline stage from `_run_pipeline_inner` into its own `Stage` implementation
- Create a stage registry that maps stage names to implementations
- Refactor `_run_pipeline_inner` to iterate over a list of stage objects instead of inlining all logic
- Preserve checkpoint-resume semantics through the new abstraction

## Capabilities

### New Capabilities
- `stage-protocol`: Uniform stage interface (protocol class, FlowContext, stage registry) that all pipeline stages implement
- `stage-extraction`: Refactor each inline pipeline stage into a discrete Stage class with typed config

### Modified Capabilities
<!-- No existing spec-level requirements are changing — this is a pure refactor of internals -->

## Impact

- **Code**: `pipeline.py` shrinks dramatically. Each stage becomes a module-level class. `models.py` gains `FlowContext`. New `stages/` package or stage classes in existing modules.
- **CLI**: No user-facing CLI changes. `harness run` behaves identically.
- **Tests**: Pipeline tests need updates to work with the new stage structure. Stage-level unit tests become possible.
- **Dependencies**: None. Pure internal refactor.
- **Blocked by**: Nothing.
- **Blocks**: `flow-templates` (needs stage interface to compose), `stage-hooks` (needs stage interface to attach hooks to).
