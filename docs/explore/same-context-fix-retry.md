# Same-Context Fix Retry

## The Idea

When review agents find issues, the original implementing worker should address them — not a fresh worker with no context. The original worker knows *why* it made each choice and can evaluate whether a finding is valid or a misunderstanding.

## Current State

The harness dispatches a fresh Claude Code worker for fix-retry. Worker B gets the findings as prompt feedback but has no memory of Worker A's reasoning. This works for obvious fixes but fails when:
- The finding is debatable and the worker needs to explain its choice
- The fix requires understanding a tradeoff the original worker navigated
- The fresh worker "fixes" the finding but introduces a different bug

## Why It Matters

Fix-retry is not a new task — it's a continuation. Fresh context is good for new work, but for refinement you want continuity.

## Discovery: `claude --resume` Works

Tested and confirmed: Claude Code CLI supports session resumption in headless mode.

```bash
# Initial dispatch returns session_id in JSON output
claude -p "implement the feature" --output-format json
# JSON includes: { "session_id": "abc123", ... }

# Resume the same session with new instructions
claude -p "address these review findings: ..." --resume abc123 --output-format json
```

The resumed session has the full conversation context — the agent remembers what it built, why it made each choice, and can evaluate review findings against its own reasoning.

### What this means for the harness

1. `dispatch_worker` already gets JSON output from claude CLI — just capture `session_id`
2. Store `session_id` on `WorkerResult`
3. `_run_review_fix_retry` uses `--resume <session_id>` instead of fresh dispatch
4. The original worker addresses its own review findings with full context

### Limitations

- Session IDs may expire (unclear retention policy)
- If the session is lost, fall back to fresh dispatch with feedback (current behavior)
- Long-running sessions may hit context limits

## Complementary Pattern: Progress Files

From Anthropic's "Effective Harnesses for Long-Running Agents" article — the `claude-progress.txt` pattern provides cross-session memory when `--resume` isn't available:

- Agent writes a progress file at the end of each session
- Next session reads it alongside `git log --oneline -20`
- Captures: what was done, what's working, what was attempted and failed

This serves as a fallback for when `--resume` can't be used (expired sessions, context limits, moving to a different runtime). See `docs/research/long-running-agent-harness-patterns.md` for full analysis.

## Possible Approaches (Updated)

1. **`--resume` session continuation** (NEAR TERM) — capture session_id, resume for fix-retry. Minimal change, high impact.
2. **Progress file** (MEDIUM TERM) — write `.harness-progress.md` between retries as fallback when `--resume` isn't available.
3. **Agent SDK** (LONGER TERM) — native session management, structured messages, conversation continuation in code.
4. **Custom runtime** (LONGEST TERM) — full control over session persistence. See `docs/explore/reproducible-agent-runtime.md`.

## Decision: Implement `--resume` First

The `--resume` approach is the clear next step:
- Already works with Claude Code CLI (verified)
- Minimal code change (capture session_id, pass to retry)
- Graceful fallback (fresh dispatch if resume fails)
- Addresses the core problem (original agent addresses its own findings)

Longer-term, progress files and/or Agent SDK will provide more robust session continuity, especially for multi-retry scenarios or when moving away from the CLI.

## Captured In

- **`session-resume`** (roadmap item 1) — OpenSpec change at `openspec/changes/session-resume/`. Covers `--resume` for both eval retries and review fix-retry, with context-aware fallback.
- **`retry-progress`** (roadmap item 2) — OpenSpec change at `openspec/changes/retry-progress/`. Covers progress file + pre-work eval as the fallback path.
