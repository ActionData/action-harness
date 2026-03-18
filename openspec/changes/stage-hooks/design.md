## Context

`WorkerEvalLoopStage` (from `composable-stages`) encapsulates the worker dispatch + eval + retry loop. OpenSpec lifecycle operations need to happen *inside* this loop: after each successful worker attempt, check off completed tasks; on full success, archive the change. These are cross-cutting concerns that shouldn't be hardcoded into the stage.

Flow templates (from `flow-templates`) provide the configuration surface — hooks are declared in YAML alongside stage config.

## Goals / Non-Goals

**Goals:**
- Hook protocol with typed callbacks for composite stage lifecycle events
- Hook registry mapping names to implementations
- OpenSpec lifecycle hooks: task updates and archival
- Flow template integration: `hooks` field in stage entries
- Hook dispatch in `WorkerEvalLoopStage`

**Non-Goals:**
- Hooks on non-composite stages (simple stages don't have internal lifecycle events worth hooking)
- Async/parallel hook execution (hooks run synchronously in order)
- User-defined hooks via shell commands (future enhancement — would enable arbitrary integrations)
- Hook error handling beyond logging (hooks are advisory, never block the pipeline)

## Decisions

### Hook protocol uses named callbacks, not a generic event system

**Decision:** Hooks implement specific named methods: `after_attempt()`, `before_redispatch()`, `on_success()`, `on_failure()`. Not a generic `on_event(event_name, payload)`.

```python
class StageHook(Protocol):
    name: str

    def after_attempt(self, context: FlowContext, attempt: int, worker_result: WorkerResult) -> None: ...
    def before_redispatch(self, context: FlowContext, attempt: int, eval_result: EvalResult) -> None: ...
    def on_success(self, context: FlowContext, final_eval: EvalResult) -> None: ...
    def on_failure(self, context: FlowContext, error: str, last_eval: EvalResult | None) -> None: ...
```

**Lifecycle timing and naming:**
- `after_attempt`: fires after each worker dispatch completes (before eval runs). All attempts, including the first. Receives `WorkerResult`. This is when the worktree has fresh commits but they haven't been evaluated yet. Named "attempt" not "retry" because it fires on all attempts.
- `before_redispatch`: fires before a retry dispatch (attempts 2+), after a failed eval. Receives the `EvalResult` that triggered the retry. Does NOT fire before the first dispatch (there's no prior eval result).
- `on_success`: fires after the final successful eval. Receives the passing `EvalResult`.
- `on_failure`: fires when retries are exhausted or the stage fails. Receives the error string and optionally the last `EvalResult`.

**Rationale:** Named callbacks are type-safe and self-documenting. The names `after_attempt` / `before_redispatch` eliminate the ambiguity of `after_retry` / `before_retry` — it's clear which fires on all attempts vs. only retries, and exactly when in the worker→eval sequence they fire.

### Hooks are advisory — never block the pipeline

**Decision:** Hook failures are logged but never stop pipeline execution. Hooks are wrapped in try/except at the dispatch point.

**Rationale:** OpenSpec task updates failing shouldn't prevent code from being merged. Hooks are observability/bookkeeping, not gates. If a hook needs to be a gate, it should be a stage.

### Hooks SHALL NOT modify pipeline-critical FlowContext fields

**Decision:** Hooks MAY read all FlowContext fields. Hooks SHALL NOT modify fields that affect pipeline control flow: `worktree_path`, `branch`, `pr_url`, `session_id`, `stages`, `baseline_eval`. The hook dispatch wrapper does not enforce this at runtime (performance cost not justified), but the contract is documented and tested.

**Rationale:** Hooks share the mutable FlowContext. An unconstrained hook could set `context.pr_url = None` and break the merge stage. Defining the safe/unsafe boundary prevents this class of bug. The constraint is documented in the StageHook Protocol docstring.

### BaseHook is a plain class, NOT a Protocol subclass

**Decision:** `BaseHook` is a plain class with concrete no-op method implementations. It does NOT inherit from `StageHook`. Hook implementations inherit from `BaseHook`. The `StageHook` Protocol is satisfied structurally — any class with matching method signatures satisfies it.

```python
# Correct:
class StageHook(Protocol):
    name: str
    def after_attempt(self, ...) -> None: ...
    # etc.

class BaseHook:  # plain class, NOT BaseHook(StageHook)
    name: str = ""
    def after_attempt(self, ...) -> None: pass  # no-op
    # etc.

class OpenSpecUpdateTasksHook(BaseHook):  # inherits from BaseHook
    name = "openspec-update-tasks"
    def after_attempt(self, ...) -> None: ...  # override
```

**Rationale:** In Python, a Protocol subclass with concrete methods becomes a runtime-checkable abstract base — not what we want. `BaseHook` as a plain class is simpler and avoids subtle Protocol inheritance bugs.

### Hooks declared in flow templates via `hooks` field

**Decision:** Stage entries in flow templates gain an optional `hooks` field mapping lifecycle event names to hook names. Phase 1 supports one hook per event (not a list).

```yaml
- stage: worker-eval-loop
  config:
    max_retries: 3
  hooks:
    after_attempt: openspec-update-tasks
    on_success: openspec-archive
```

**Rationale:** This keeps hook configuration declarative and co-located with the stage it applies to. The flow runner resolves hook names from the hook registry at parse time.

**Phase 1 constraint:** One hook per event per stage. Multiple hooks per event (`after_attempt: [hook-a, hook-b]`) raises a validation error. Future enhancement will support lists.

**Cross-change note:** This adds a `hooks` field to `StageEntry` defined in the `flow-templates` change. This change includes a delta spec for the flow-schema capability to formalize the addition.

### OpenSpec hooks use the existing openspec CLI/modules

**Decision:** `openspec-update-tasks` reads the worktree's tasks.md and compares checkbox state against the source repo's tasks.md. `openspec-archive` calls existing archival logic from `openspec_reviewer.py`.

**Task diff algorithm:**
1. Derive source path: `context.repo / "openspec" / "changes" / context.change_name / "tasks.md"`
2. Derive worktree path: `context.worktree_path / "openspec" / "changes" / context.change_name / "tasks.md"`
3. Read both files line-by-line
4. For each line matching `- [ ]` in source and `- [x]` in worktree (same line position): update the source line to `- [x]`
5. Only promote `[ ]` → `[x]`. Never demote `[x]` → `[ ]` (a later retry that reverts doesn't uncomplete tasks)
6. Write updated source file

**Rationale:** Line-by-line checkbox comparison is deterministic and safe. The one-way promotion rule prevents races where a later retry's worker unchecks tasks that were completed in an earlier attempt. This also means the hook is idempotent — running it twice produces the same result.

### openspec-archive replaces OpenSpecReviewStage archival for hooked flows

**Decision:** When the `openspec-archive` hook is configured on `worker-eval-loop`, the `OpenSpecReviewStage` skips its own archival step (it still runs validation and semantic review). The hook archives earlier in the pipeline — immediately after the worker-eval loop succeeds — rather than waiting for the review stage.

**Rationale:** Prevents double-archival. The review stage can detect that archival already happened by checking if the change directory still exists. If it doesn't, it logs "already archived by hook" and skips that step.

## Risks / Trade-offs

**[Risk] Hook ordering matters when multiple hooks attach to the same event** → For phase 1, only one hook per event per stage. Validation rejects lists. Document that future multi-hook support will execute in declaration order.

**[Risk] openspec-update-tasks diffing produces wrong results** → Mitigated by the one-way promotion rule and line-position matching. The hook never unchecks tasks and only modifies lines that changed from `[ ]` to `[x]` at the same position. Test coverage includes: checkbox promotion, no-change no-op, prompt mode no-op, and the "later retry reverts a checkbox" scenario (verify source stays `[x]`).

**[Trade-off] Hooks only on composite stages vs. all stages** → Limiting hooks to composite stages keeps the surface small. Simple stages are... simple. If a use case for hooks on simple stages emerges, the protocol can be extended.

**[Trade-off] No runtime enforcement of FlowContext mutation contract** → Documented, tested, but not enforced. A misbehaving hook could still break things. Acceptable for phase 1 where all hooks are built-in and reviewed.
