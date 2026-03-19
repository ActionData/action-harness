## Why

When the harness dispatches workers to external repos, the target repo doesn't have the harness's Claude Code skills (like `opsx:apply`, `opsx:explore`, etc.). Workers dispatched to self-hosting (this repo) happen to work because `.claude/skills/` already exists. But for any other repo, the worker can't invoke OpenSpec skills — the system prompt tells it to "run the opsx:apply skill" but the skill files aren't present in the worktree.

This is the key gap blocking reliable multi-repo use: the worker's system prompt references skills that don't exist in the target environment.

## What Changes

- Add a `skills.py` module that discovers harness skills from `.claude/skills/` in the harness source tree
- Add a function to inject (copy) skills into a target worktree's `.claude/skills/` directory before dispatch
- Integrate skill injection into the worker dispatch flow in `pipeline.py`
- Target repo skills take precedence — never overwrite existing skills
- Add cleanup tracking so injected skills can be identified (via a `.harness-injected` marker)

## Capabilities

### New Capabilities
- `skill-injection`: Discover and copy harness skills into target repo worktrees before worker dispatch. Target repo skills take precedence. Marker file tracks what was injected for diagnostics.

### Modified Capabilities
- Worker dispatch: `_run_pipeline_inner` calls skill injection before `dispatch_worker()` when the worktree is for an external repo

## Impact

- **Code**: New `skills.py` module (~100 lines). Small integration point in `pipeline.py`.
- **CLI**: No user-facing CLI changes. `--verbose` logs skill injection details.
- **Tests**: Unit tests for skill discovery, injection, and precedence logic.
- **Dependencies**: None. Uses pathlib and shutil only.
- **Blocked by**: Nothing.
- **Blocks**: Nothing directly, but enables reliable multi-repo OpenSpec workflows.
