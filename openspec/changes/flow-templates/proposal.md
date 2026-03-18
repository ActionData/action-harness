## Why

With `composable-stages` providing discrete stage objects, the pipeline still assembles them in hardcoded Python. Users who want a lightweight flow for small changes or a review-only flow for existing PRs have no option — it's the full 9-stage pipeline or nothing. Flow templates let users define custom stage sequences in YAML, and let harness ship sensible presets (standard, quick) that cover common workflows without code changes.

## What Changes

- Define a YAML schema for flow templates (stage list with config, parallel blocks, conditional execution)
- Build a deterministic flow runner that reads a template and executes stages in order
- Ship bundled flows: `standard` (current behavior), `quick` (worker + eval + PR, no review)
- Add `--flow <name>` flag to `harness run` to select a flow template
- Support repo-level custom flows in `.harness/flows/` that override or extend bundled flows
- Build a `checkout-pr` stage and ship a `review-only` flow as proof the abstraction supports non-standard flows

## Capabilities

### New Capabilities
- `flow-schema`: YAML schema for defining flow templates with stages, parallel blocks, conditionals, and per-stage config
- `flow-runner`: Deterministic runner that reads a flow template and executes stages via the stage registry
- `flow-resolution`: Resolution logic for finding flows (repo `.harness/flows/` overrides bundled, `--flow` flag selects)
- `checkout-pr-stage`: New stage that checks out an existing PR branch for review-only workflows

### Modified Capabilities
<!-- No existing spec-level requirements are changing -->

## Impact

- **Code**: New `flow_runner.py` module, new `checkout_pr.py` stage, bundled YAML files in package data. `cli.py` gains `--flow` flag.
- **CLI**: New `--flow` option on `harness run`. Default is `standard` (identical to current behavior). Breaking: None — omitting `--flow` preserves existing behavior.
- **Dependencies**: PyYAML (or use stdlib tomllib if YAML is too heavy — but YAML is more natural for this).
- **Blocked by**: `composable-stages` (needs Stage protocol and stage registry).
- **Blocks**: Agentic orchestrator (future — needs flow templates as the guide/constraint).
