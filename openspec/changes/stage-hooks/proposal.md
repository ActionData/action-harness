## Why

Composite stages like `worker-eval-loop` encapsulate their retry logic, but there's no way to inject behavior between retries or on completion. OpenSpec lifecycle tasks (checking off tasks after implementation, archiving on completion, updating specs) need to run *inside* the worker-eval loop — not as a separate stage that runs after. Without hooks, these cross-cutting concerns would have to be hardcoded into the composite stage, coupling it to OpenSpec and preventing other uses (custom notifications, metrics, etc.).

## What Changes

- Define a hook protocol for composite stages: `after_attempt`, `before_redispatch`, `on_success`, `on_failure`
- Create a hook registry that maps hook names to implementations
- Build OpenSpec lifecycle hooks: `openspec-update-tasks` (check off completed tasks after each worker attempt), `openspec-archive` (archive change on full completion)
- Add `hooks` field to flow template stage entries (delta modification to `flow-templates` flow-schema capability)
- Wire hooks into `WorkerEvalLoopStage`

## Capabilities

### New Capabilities
- `stage-hook-protocol`: Hook interface for composite stages with after-attempt, before-redispatch, success, and failure callbacks
- `openspec-lifecycle-hooks`: Built-in hooks for OpenSpec task tracking and archival during pipeline execution

### Modified Capabilities
- `flow-schema`: Adding optional `hooks` field to stage entries in flow templates (delta spec for capability defined in `flow-templates` change)

## Impact

- **Code**: New hook protocol in `stage.py`, hook registry, OpenSpec hook implementations. `WorkerEvalLoopStage` gains hook dispatch points. Flow schema gains `hooks` field.
- **CLI**: No new CLI flags. Hooks are configured via flow templates.
- **Dependencies**: None beyond what `composable-stages` introduces.
- **Blocked by**: `composable-stages` (needs Stage protocol and WorkerEvalLoopStage). Partially depends on `flow-templates` for the `hooks` field in flow template YAML — hook protocol and registry can be built in parallel, but flow template integration requires `flow-templates` to land first.
- **Blocks**: Nothing currently planned.
