## 1. Stage Protocol and FlowContext

- [ ] 1.1 Create `src/action_harness/stage.py` with `Stage` Protocol (`name: str`, `composite: bool`, `run(context: FlowContext) -> StageResult`), `FlowContext` dataclass, and per-stage `TypedDict` configs (`WorkerEvalLoopConfig`, `ReviewAgentsConfig`, etc.). Config is constructor-injected, not passed to `run()`.
- [ ] 1.2 Create stage registry: `STAGE_REGISTRY` dict, `register_stage()`, and `get_stage()` functions in `stage.py`
- [ ] 1.3 Add unit tests for FlowContext construction, stage registry lookup, and unknown stage error

## 2. Extract Stage Implementations

- [ ] 2.1 Create `WorktreeStage` — extract worktree creation and checkpoint restoration from the worktree block in `_run_pipeline_inner` (the block starting with `if _should_run_stage("worktree", checkpoint)`). Non-composite. Register as `"worktree"`.
- [ ] 2.2 Create `WorkerEvalLoopStage` — extract worker dispatch, baseline eval, eval loop, retry logic, session resume, and progress file management (the block from worktree-complete through eval-loop-end). Composite stage: appends its own `WorkerResult` and `EvalResult` entries to `context.stages`. Register as `"worker-eval-loop"`.
- [ ] 2.3 Create `CreatePrStage` — extract git push, PR creation, rollback tags, issue linking (the block starting with `create_pr()` call). Non-composite. Register as `"create-pr"`.
- [ ] 2.4 Create `ProtectedPathsStage` — extract protected paths check and PR flagging (the block calling `check_protected_files()`). Non-composite, returns `PrResult(success=True)`. Register as `"protected-paths"`.
- [ ] 2.5 Create `ReviewAgentsStage` — extract review dispatch, tolerance triage, fix-retry loop, PR comments (the block starting with review agent dispatch). Composite stage: appends its own `ReviewResult` entries. Register as `"review-agents"`.
- [ ] 2.6 Create `OpenSpecReviewStage` — extract openspec review dispatch, archival, prompt-mode skip (the block calling `dispatch_openspec_review()`). Non-composite. Register as `"openspec-review"`.
- [ ] 2.7 Create `MergeGateStage` — extract merge gate checks and conditional merge (the block calling `check_merge_gates()`). Non-composite. Register as `"merge-gate"`.

## 3. Refactor Pipeline Runner

- [ ] 3.1 Refactor `_run_pipeline_inner` to build a list of Stage objects and iterate over them, passing FlowContext. For non-composite stages, the runner appends the returned result to `context.stages`. For composite stages (`stage.composite == True`), the runner does NOT append (stage manages its own). Remove all inlined stage logic.
- [ ] 3.2 Update `run_pipeline` to construct FlowContext from CLI parameters and pass it through
- [ ] 3.3 Widen `PipelineCheckpoint.completed_stage` from `Literal[...]` to `str`. Remove `MacroStage` type alias. Add a `_CHECKPOINT_NAME_COMPAT` dict mapping old names to new: `{"worker_eval": "worker-eval-loop", "pr": "create-pr", "review": "review-agents", "openspec_review": "openspec-review"}`. Update `_should_run_stage` to check this compat dict when loading old checkpoints.

## 4. Validation

- [ ] 4.1 Run full test suite — all existing pipeline tests must pass unchanged (behavior preservation)
- [ ] 4.2 Run `ruff check`, `ruff format --check`, and `mypy src/` — no regressions
- [ ] 4.3 Verify dry-run output matches pre-refactor output
