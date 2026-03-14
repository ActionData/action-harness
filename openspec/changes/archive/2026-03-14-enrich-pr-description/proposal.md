## Why

The harness opens PRs with minimal descriptions — just the change name and eval pass/fail. A human reviewing PR #11 (the first self-hosted PR) sees no context about what was implemented, what files changed, or what the change was about. The PR body should give the reviewer enough context to evaluate the change without reading the full diff blind.

## What Changes

- Thread `WorkerResult` and the repo path through to `_build_pr_body` so the PR body has access to worker output and the worktree for git operations
- Include the proposal summary from `openspec/changes/<name>/proposal.md` (the "Why" section)
- Include `git diff --stat` output showing files changed
- Include commit messages from the worktree branch
- Include worker cost and duration if available
- Include the worker's self-reported observations (from `WorkerResult.worker_output`)

## Capabilities

### New Capabilities

- `pr-description`: Structured PR body generation that includes proposal context, diff summary, commit messages, worker observations, eval results, and cost metadata.

### Modified Capabilities

## Impact

- `src/action_harness/pr.py` — `_build_pr_body` gains new inputs and richer output
- `src/action_harness/pipeline.py` — thread `WorkerResult` to `create_pr`
- `tests/test_pr.py` — update body construction tests for new sections
- `tests/test_integration.py` — update mocks if `create_pr` signature changes
