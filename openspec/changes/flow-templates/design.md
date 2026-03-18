## Context

After `composable-stages`, each pipeline stage is a discrete object with a uniform interface. But the stage list is still assembled in Python inside `_run_pipeline_inner`. Flow templates externalize this assembly into YAML, making it declarative and user-configurable.

The harness already uses YAML for protected paths (`.harness/protected-paths.yml`) and agent definitions (`.harness/agents/*.md` with YAML frontmatter), so YAML is a natural fit.

## Goals / Non-Goals

**Goals:**
- YAML schema for flow templates with stages, parallel blocks, and conditionals
- Deterministic runner that executes a parsed flow template
- Bundled flows: `standard`, `quick`, `review-only`
- `--flow` CLI flag for flow selection
- Flow resolution: repo `.harness/flows/` → bundled flows → error
- `checkout-pr` stage for review-only workflows

**Non-Goals:**
- Flow-level inputs / variable templating (`{{ inputs.x }}`) — future enhancement
- `fan-out` / dynamic parallelism — future enhancement
- Agentic orchestrator mode — future enhancement
- Flow validation CLI command — nice-to-have, not required for phase 1

## Decisions

### YAML schema uses a flat stage list with block-level primitives

**Decision:** Flows are a list of entries. Each entry is either a `stage` (single), a `parallel` block (concurrent stages), or has a `when` condition. No nesting beyond one level.

```yaml
name: standard
description: Full implementation pipeline with review

stages:
  - stage: worktree
  - stage: worker-eval-loop
    config:
      max_retries: 3
  - stage: create-pr
  - parallel:
      - stage: protected-paths
      - stage: review-agents
        config:
          agents: [bug-hunter, test-reviewer, quality-reviewer]
  - stage: openspec-review
    when: is_openspec_change
  - stage: merge-gate
    when: auto_merge
```

**Rationale:** One level of nesting (parallel blocks) covers the known use cases without introducing a full DAG engine. `when` conditions use named predicates evaluated against FlowContext, not arbitrary expressions — keeps it auditable.

**Alternative considered:** Full DAG with explicit edges. Rejected — overkill for sequential-with-parallelism flows, and harder to read/write.

### Parallel blocks use threading, not multiprocessing

**Decision:** `parallel:` blocks dispatch stages in `concurrent.futures.ThreadPoolExecutor`. Each stage gets its own thread but shares the `FlowContext`.

**Rationale:** Stages are I/O-bound (subprocess calls). Threads are simpler than processes for shared state. The current review agent dispatch already uses threading. FlowContext writes in parallel blocks must be to disjoint fields (e.g., protected-paths writes `protected_files`, review-agents writes review results) — document this as a contract.

### `when` conditions are named predicates, not expressions

**Decision:** `when` values are predefined predicate names: `is_openspec_change`, `auto_merge`, `has_pr`. The runner evaluates them against FlowContext.

```python
PREDICATES: dict[str, Callable[[FlowContext], bool]] = {
    "is_openspec_change": lambda ctx: ctx.prompt is None,
    "auto_merge": lambda ctx: ctx.auto_merge,
    "has_pr": lambda ctx: ctx.pr_url is not None,
}
```

**Rationale:** Named predicates are safe, auditable, and sufficient. Arbitrary expressions (Jinja, Python eval) are security risks and debugging nightmares. New predicates can be added to the registry as needed.

### Flow resolution: repo overrides bundled, CLI selects

**Decision:** Resolution order:
1. `.harness/flows/<name>.yml` in the target repo
2. Bundled flows shipped with action-harness package
3. Error if not found

`--flow <name>` selects. Default is `standard`.

**Rationale:** Repo-level overrides let teams customize without forking. Bundled defaults cover common cases. Same pattern as agent definitions (`.harness/agents/` overrides built-in).

### Bundled flows ship as package data

**Decision:** Bundled flow YAML files live in `src/action_harness/flows/` and are included via `pyproject.toml` package data. Loaded via `importlib.resources`.

**Rationale:** Keeps flows versioned with the code. `importlib.resources` is the standard way to access package data in modern Python.

### checkout-pr stage resolves PR to a local worktree

**Decision:** `CheckoutPrStage` takes a PR URL or number, fetches the branch via `gh pr checkout`, and sets `context.worktree_path` and `context.branch`. It uses `git worktree add` pointed at the PR's head branch.

**Rationale:** Review-only flows need a worktree to run review agents against. Reusing the worktree abstraction keeps the stage compatible with the rest of the pipeline.

## Risks / Trade-offs

**[Risk] YAML schema evolves and breaks existing flow files** → Version the schema. Add a `schema_version: 1` field to flow files. Runner validates version before executing.

**[Risk] Parallel blocks with shared FlowContext cause race conditions** → Document the contract: parallel stages MUST write to disjoint FlowContext fields. Each stage class declares an `output_fields: frozenset[str]` class attribute listing which FlowContext fields it writes. The flow parser validates at parse time that no two stages in a parallel block share output fields. If overlap is detected, parsing raises a validation error naming the conflicting stages and fields.

**[Risk] PyYAML dependency adds attack surface** → Use `yaml.safe_load()` exclusively. Never `yaml.load()` or `yaml.unsafe_load()`. PyYAML is already a transitive dependency via several packages in the ecosystem. The flow parser SHALL use `yaml.safe_load()` for all YAML parsing.

**[Trade-off] Named predicates vs. flexibility** → Named predicates are less flexible than expressions but dramatically safer. If a new condition is needed, adding a predicate is a one-line change.
