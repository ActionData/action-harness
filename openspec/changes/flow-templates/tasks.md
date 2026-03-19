## 1. Flow Schema and Parser

- [ ] 1.1 Add PyYAML to project dependencies in `pyproject.toml`
- [ ] 1.2 Create `src/action_harness/flow_schema.py` with Pydantic models: `FlowTemplate`, `StageEntry`, `ParallelBlock`. Parse YAML via `yaml.safe_load()` (never `yaml.load()`). Validate stage names against stage registry, predicate names against predicate registry. Validate parallel blocks for output field overlap using each stage's `output_fields` class attribute.
- [ ] 1.3 Create predicate registry in `flow_schema.py`: `is_openspec_change` (True when `ctx.prompt is None`), `auto_merge` (True when `ctx.auto_merge`), `has_pr` (True when `ctx.pr_url is not None`) — each with `FlowContext -> bool` signature
- [ ] 1.4 Add unit tests for flow schema parsing: valid flows, missing fields, unknown stages, unknown predicates, parallel blocks, parallel output field overlap rejection, safe_load usage

## 2. Flow Runner

- [ ] 2.1 Create `src/action_harness/flow_runner.py` with `run_flow(template: FlowTemplate, context: FlowContext) -> PrResult` that iterates stages, handles parallel blocks via ThreadPoolExecutor, evaluates `when` predicates, integrates with checkpoint-resume, and handles composite vs non-composite result appending (runner appends for non-composite, skips for composite)
- [ ] 2.2 Add event logging to flow runner: `flow.started`, `stage.started`, `stage.completed`, `stage.skipped`, `parallel.started`, `parallel.completed`, `flow.completed`
- [ ] 2.3 Add unit tests for flow runner: sequential execution, conditional skipping, parallel blocks, stage failure stops pipeline, checkpoint resume, composite stage result handling

## 3. Bundled Flows

- [ ] 3.1 Create `src/action_harness/flows/` package directory with `__init__.py`
- [ ] 3.2 Create `src/action_harness/flows/standard.yml` — equivalent to current pipeline behavior (all 7 stages, `openspec-review` with `when: is_openspec_change`, `merge-gate` with `when: auto_merge`)
- [ ] 3.3 Create `src/action_harness/flows/quick.yml` — worktree, worker-eval-loop (max_retries: 1), create-pr
- [ ] 3.4 Create `src/action_harness/flows/review-only.yml` — checkout-pr, review-agents
- [ ] 3.5 Update `pyproject.toml` to include `flows/*.yml` as package data

## 4. Flow Resolution

- [ ] 4.1 Create `resolve_flow(name: str, repo: Path) -> FlowTemplate` in `flow_schema.py` — searches `.harness/flows/<name>.yml` in repo, then bundled flows via `importlib.resources`, raises error with available flows if not found
- [ ] 4.2 Add unit tests for flow resolution: repo override, bundled fallback, not-found error with available list

## 5. Checkout-PR Stage

- [ ] 5.1 Create `src/action_harness/checkout_pr.py` with `CheckoutPrStage` — resolves PR via `gh pr view --json headRefName`, creates worktree from PR head branch via `git worktree add`, sets `context.worktree_path`, `context.branch`, and `context.pr_url`. Non-composite.
- [ ] 5.2 Register `checkout-pr` in stage registry
- [ ] 5.3 Add unit tests for CheckoutPrStage: successful checkout (assert `context.worktree_path` is set and exists), PR not found error (assert `success=False` with error message)

## 6. CLI Integration

- [ ] 6.1 Add `--flow` option to `harness run` command in `cli.py` (default: `"standard"`, type: `str`, help text explaining flow selection)
- [ ] 6.2 Wire flow into `run_pipeline`: call `resolve_flow(flow_name, repo)` to get `FlowTemplate`, construct stages from template entries (instantiating each with its config dict), construct `FlowContext` from CLI parameters, call `run_flow(template, context)`. The existing `run_pipeline` function becomes a thin wrapper: FlowContext construction + flow resolution + `run_flow` delegation + manifest writing.
- [ ] 6.3 Update `--dry-run` output to show selected flow name and stage list (stage names in execution order, with `[parallel]` markers and `[when: predicate]` annotations)
- [ ] 6.4 Update CLI help text and docstrings to document `--flow`

## 7. Validation

- [ ] 7.1 Run full test suite — existing tests pass (default `standard` flow produces identical behavior)
- [ ] 7.2 Run `ruff check`, `ruff format --check`, `mypy src/` — no regressions
- [ ] 7.3 Manual test: `harness run --flow quick --dry-run` shows correct stage list
- [ ] 7.4 Manual test: `harness run --flow review-only --dry-run` shows checkout-pr + review-agents
