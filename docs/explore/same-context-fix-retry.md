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

## Technical Blockers

- Claude Code CLI `-p` mode doesn't support session resumption
- Each invocation is independent — no conversation history carries over
- The Claude Code SDK may support conversation continuation (needs investigation)
- A custom agent runtime would give full control over session management

## Possible Approaches

1. **Agent SDK** — switch from CLI to SDK for worker dispatch, use conversation continuation
2. **Context dump** — have Worker A output a "reasoning summary" as its last message, feed it to Worker B as additional context
3. **Custom runtime** — build the agent loop directly against the Anthropic API with session persistence
4. **Hybrid** — CLI for initial dispatch, SDK for fix-retry with conversation history from the CLI's output

## Decision: Deferred

Needs investigation into Agent SDK conversation capabilities. For now, fresh dispatch works for most cases. The strict-review-triage change (now merged) ensures all findings are addressed, even if by a fresh worker.
