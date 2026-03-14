## Why

The harness is built by agents and debugged by agents. When a pipeline run fails, the debugging agent needs to understand what happened — which stage failed, what inputs it received, what it produced, and why. Today, the bootstrap spec (reframe-pipeline) has no logging, no structured output from pipeline stages, and no way to run stages independently. The first self-hosted tasks will fail, and when they do, the agent diagnosing the failure will be flying blind.

This must be addressed during bootstrap, not deferred to the structured-logging self-hosted task. The self-hosted task upgrades logging to JSON and adds dashboards. This change ensures the bootstrap itself is diagnosable from day one.

## What Changes

- Add a design rule to CLAUDE.md: every function that performs I/O must be agent-debuggable — stderr progress for humans, structured return values for programmatic consumption
- Add a design rule to CLAUDE.md: pipeline stages must be independently callable — the CLI wires them together, but each stage is testable and runnable in isolation
- Establish conventions (via CLAUDE.md rules and result models) that the reframe-pipeline implementing agent follows — no modifications to reframe-pipeline tasks, the CLAUDE.md rules and result models are sufficient
- Define result model types in `models.py` that every pipeline function returns — structured data, not just side effects
- Add a `--verbose` flag to the CLI for detailed stderr output during pipeline runs
- Add a `--dry-run` flag to the CLI that validates inputs and prints what would happen without executing

## Capabilities

### New Capabilities

- `agent-debuggability`: Design rules, logging conventions, and CLI flags that make the harness observable and testable by agents. Covers stderr logging, structured return values, stage isolation, and dry-run support.

### Modified Capabilities


## Impact

- `CLAUDE.md` — new design rules added
- `src/action_harness/cli.py` — new `--verbose` and `--dry-run` flags
- Reframe-pipeline implementation follows the new CLAUDE.md rules (no task modifications needed — rules apply to all code)
- `src/action_harness/models.py` — result model types for all pipeline stages
