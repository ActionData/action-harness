## Why

When `--resume` isn't available (expired session, context exhaustion, CLI failure), the retry loop falls back to a fresh dispatch with only the eval error as feedback. The worker has no memory of what the prior dispatch attempted — what commits were made, what approach was taken, what files were modified. It may repeat the same failed approach.

A progress file written to the worktree between dispatches gives the next worker curated context about prior attempts. Combined with pre-work verification (running eval before the worker starts on retries), this ensures the worker starts from a known state with full knowledge of what was tried.

Inspired by the `claude-progress.txt` pattern from Anthropic's "Effective Harnesses for Long-Running Agents" engineering blog post.

## What Changes

- Write a `.harness-progress.md` file in the worktree after each worker dispatch, summarizing: commits made, eval results, approach taken, what failed
- Workers read this file at dispatch start (injected into prompt or read by the worker via CLAUDE.md convention)
- Run eval *before* the worker on retries (pre-work verification) to catch broken state early
- Progress file accumulates across retries (each dispatch appends its section)

## Capabilities

### New Capabilities
- `retry-progress`: Write and read per-worktree progress files between worker dispatches, plus pre-work eval verification on retries.

### Modified Capabilities
None

## Prerequisites

This change can be implemented independently of `session-resume`. Both modify the retry loop in `_run_pipeline_inner()`, but they are additive — progress files are written regardless of whether `--resume` is used. If both land, `session-resume` should merge first (it's simpler), and this change layers on top. The progress file becomes the fallback when `--resume` isn't available.

## Impact

- `pipeline.py` — write progress file after worker dispatch + eval, run pre-work eval on retries
- `worker.py` — include progress file contents in the worker prompt (when file exists)
- New utility function for progress file writing
- No changes to models, CLI, or PR modules
