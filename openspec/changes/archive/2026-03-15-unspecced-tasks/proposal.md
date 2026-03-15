## Why

The harness currently requires a full OpenSpec change — the worker prompt is hardcoded to "implement the OpenSpec change '{change_name}' using the opsx:apply skill." This means every task, no matter how small, needs a proposal, design, specs, and tasks before the harness can work on it.

Many tasks don't need that ceremony: "fix the auth bug in issue #42", "update the README", "bump the dependency version." These are clear, scoped tasks where the overhead of creating OpenSpec artifacts exceeds the implementation effort.

Adding a `--prompt` flag lets the harness accept freeform tasks. Everything else — worktree isolation, eval, retry, PR creation, review — stays the same.

## What Changes

- New `--prompt` flag on `harness run` as an alternative to `--change`
- Exactly one of `--prompt` or `--change` must be provided (mutually exclusive)
- When `--prompt` is used, the worker receives the prompt directly instead of opsx:apply instructions
- `build_system_prompt()` adapts to produce a generic implementation prompt rather than an OpenSpec-specific one
- `validate_inputs()` skips the OpenSpec change directory check when `--prompt` is used
- Pipeline, eval, retry, PR creation, and review all work unchanged
- OpenSpec review stage is skipped when `--prompt` is used (no change to archive)

## Capabilities

### New Capabilities
- `freeform-prompt`: Accept a `--prompt` flag on `harness run` that sends a freeform task description to the worker instead of an opsx:apply instruction. Mutually exclusive with `--change`.

### Modified Capabilities
None — no existing spec-level behavior changes. The pipeline, worker, and PR modules gain new code paths but their existing behavior is unchanged.

## Impact

- `cli.py` — add `--prompt` flag, make `--change` optional, add mutual exclusion validation
- `worker.py` — `build_system_prompt()` needs a prompt-mode variant that gives the worker a generic implementation role instead of the OpenSpec-specific one
- `pipeline.py` — `run_pipeline()` needs to accept an optional prompt parameter and pass it through to the worker. Skip OpenSpec review stage when no change name is provided.
- `pr.py` — PR title/description needs to handle the no-change-name case (use a summary of the prompt instead)
- `validate_inputs()` — skip the change directory check when in prompt mode
