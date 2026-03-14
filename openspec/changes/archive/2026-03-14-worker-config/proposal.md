## Why

The harness currently hardcodes Claude Code CLI flags (max-turns, output format). There is no way to specify the model, effort level, budget cap, or permission mode. Different tasks benefit from different configurations — a simple flag addition needs less compute than a multi-file refactor. The operator should be able to tune these per invocation.

## What Changes

- Add CLI flags to `action-harness run`: `--model`, `--effort`, `--max-budget-usd`, `--permission-mode`
- Pass these through to the `claude` CLI invocation in `dispatch_worker`
- Include configured values in `--dry-run` output and PR body metadata
- Default values chosen for the bootstrap use case (self-hosting on own repo)

## Capabilities

### New Capabilities

- `worker-config`: CLI flags and worker dispatch configuration for Claude Code model, effort, budget, and permission mode. Flows through from CLI to worker invocation to PR metadata.

### Modified Capabilities

## Impact

- `src/action_harness/cli.py` — new CLI options
- `src/action_harness/worker.py` — new params on `dispatch_worker`, added to `claude` CLI command
- `src/action_harness/pipeline.py` — thread new params through
- `tests/test_worker.py` — verify flags appear in command construction
- `tests/test_cli.py` — dry-run includes new values, help shows new flags
