## Why

The pipeline currently ends after creating a PR and running review agents. A human must manually merge every PR, even when all quality gates pass — eval clean, review agents clean, OpenSpec review approved. This bottleneck defeats the purpose of autonomous operation and blocks the harness from self-hosting through to completion.

Auto-merge closes the loop: when all gates pass and no protected paths are touched, the harness merges its own PR. When protected paths are involved, the PR is flagged for human review instead.

## What Changes

- New `--auto-merge` flag on `harness run` (default off — opt-in)
- After all review stages pass, the pipeline merges the PR via `gh pr merge`
- Protected paths block auto-merge — if the PR touches protected files, skip merge and flag for human review
- Remaining review findings block auto-merge — only merge when the final review round is clean
- New pipeline stage: `merge` (after openspec-review, before pipeline completion)
- CI check: optionally wait for CI status checks to pass before merging

## Capabilities

### New Capabilities
- `auto-merge`: Automatically merge PRs via `gh pr merge` when all quality gates pass. Blocked by protected paths and remaining review findings. Opt-in via `--auto-merge` flag.

### Modified Capabilities
None

## Impact

- `cli.py` — add `--auto-merge` flag to `run` command
- `pipeline.py` — new merge stage after openspec-review, gated on: no remaining review findings, no protected files, auto-merge enabled
- `models.py` — new `MergeResult` stage model (or extend `PrResult`)
- No changes to worker, eval, review agents, or worktree modules
