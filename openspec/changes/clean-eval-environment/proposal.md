## Why

The harness's own `VIRTUAL_ENV` environment variable leaks into eval subprocess calls. When running eval on a target repo, `uv` and `ruff` see the harness's venv path and warn: `VIRTUAL_ENV=/Users/.../action-harness/.venv does not match the project environment path .venv`. This is confusing and could cause tools to use the wrong Python environment.

## What Changes

- Strip `VIRTUAL_ENV` (and `VIRTUAL_ENV_PROMPT`) from the environment when running eval commands in the worktree
- Ensure eval commands use the target repo's environment, not the harness's

## Capabilities

### New Capabilities

- `clean-eval-environment`: Eval commands run in a clean environment without the harness's VIRTUAL_ENV leaking into target repo subprocesses.

### Modified Capabilities

## Impact

- `src/action_harness/evaluator.py` — strip VIRTUAL_ENV from subprocess env
- `tests/test_evaluator.py` — verify env cleaning
