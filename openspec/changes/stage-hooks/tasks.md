## 1. Hook Protocol and Registry

- [ ] 1.1 Add `StageHook` Protocol to `src/action_harness/stage.py` with four methods: `after_attempt(context, attempt, worker_result)`, `before_redispatch(context, attempt, eval_result)`, `on_success(context, final_eval)`, `on_failure(context, error, last_eval)`. Add `BaseHook` as a plain class (NOT inheriting from StageHook) with no-op defaults for all four methods.
- [ ] 1.2 Create hook registry in `stage.py`: `HOOK_REGISTRY` dict, `register_hook()`, `get_hook()` functions
- [ ] 1.3 Add unit tests for hook registry: registration, lookup, unknown name error. Add test that `BaseHook` does NOT appear in `StageHook.__mro__` (verifying it's a plain class, not a Protocol subclass).

## 2. Hook Dispatch in WorkerEvalLoopStage

- [ ] 2.1 Add `hooks` parameter to `WorkerEvalLoopStage.__init__` — accepts a dict mapping lifecycle event names to `StageHook` instances
- [ ] 2.2 Add hook dispatch calls at four lifecycle points in the retry loop: `after_attempt` (after worker dispatch, before eval — all attempts), `before_redispatch` (before retry dispatch, after failed eval — attempts 2+ only), `on_success` (after final passing eval), `on_failure` (retries exhausted or stage error). Wrap each in try/except with stderr logging.
- [ ] 2.3 Add unit tests: (1) Assert `after_attempt` called N times for N attempts. (2) Assert `before_redispatch` called N-1 times. (3) Assert `on_success` called once on success. (4) Assert `on_failure` called once with error string on failure. (5) Assert hook exception is logged to stderr but pipeline continues. (6) Assert no hooks configured produces identical behavior to unhooked stage.

## 3. Flow Template Hook Integration

- [ ] 3.1 Add optional `hooks` field to `StageEntry` in `flow_schema.py` — `dict[str, str]` mapping event name to hook registry name. Validate event names against the four lifecycle methods. Validate hook names against hook registry.
- [ ] 3.2 Update flow parser to resolve hook names from registry and pass hook instances to stage constructors
- [ ] 3.3 Add validation: unknown hook names raise parse error. Multiple hooks per event (list value) raises validation error with "only one hook per event supported" message.
- [ ] 3.4 Add unit tests for hook declaration in YAML: valid hooks parsed, unknown hook name error, list-of-hooks rejected

## 4. OpenSpec Lifecycle Hooks

- [ ] 4.1 Create `src/action_harness/openspec_hooks.py` with `OpenSpecUpdateTasksHook(BaseHook)`. Implementation: read source tasks.md at `context.repo / "openspec" / "changes" / context.change_name / "tasks.md"`, read worktree tasks.md at `context.worktree_path / "openspec" / "changes" / context.change_name / "tasks.md"`. Compare line-by-line: for each line where source has `- [ ]` and worktree has `- [x]`, update source to `- [x]`. Never demote `[x]` to `[ ]`. If either file doesn't exist, return silently.
- [ ] 4.2 Create `OpenSpecArchiveHook(BaseHook)` in same module. On `on_success`: if `context.prompt` is set, return silently. Read source tasks.md, count unchecked tasks. If all checked, call existing archival logic from `openspec_reviewer.py`. If not all checked, log remaining count to stderr.
- [ ] 4.3 Register both hooks as `openspec-update-tasks` and `openspec-archive`
- [ ] 4.4 Update bundled `standard.yml` flow to attach OpenSpec hooks to worker-eval-loop stage: `hooks: {after_attempt: openspec-update-tasks, on_success: openspec-archive}`
- [ ] 4.5 Add unit tests with specific assertions: (1) Source tasks.md line `- [ ] 2.1 implement X` becomes `- [x] 2.1 implement X` after hook fires, while `- [ ] 2.2 implement Y` stays unchanged. (2) Source `- [x] 1.1 done` stays `- [x]` even when worktree has `- [ ] 1.1 done` (one-way promotion). (3) When source has an extra task not in worktree, that line is preserved unchanged. (4) Hook returns without modifying source when worktree tasks.md doesn't exist. (5) Hook returns without modifying source when `context.prompt is not None`. (6) `openspec-archive` calls archival logic when all checkboxes are `[x]`. (7) `openspec-archive` does NOT call archival when any checkbox is `[ ]` and logs remaining count.

## 5. Validation

- [ ] 5.1 Run full test suite — all existing tests pass
- [ ] 5.2 Run `ruff check`, `ruff format --check`, `mypy src/` — no regressions
- [ ] 5.3 Integration smoke test: create a minimal flow template with `hooks: {after_attempt: openspec-update-tasks}`, run `WorkerEvalLoopStage` with a mock worker that checks off a task in the worktree tasks.md, assert the source tasks.md is updated with the checkbox change
