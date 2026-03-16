## Why

Every worker dispatch is currently a fresh Claude Code invocation. When eval fails and the worker retries, the new worker has no memory of what the previous dispatch tried — it only gets the eval error as feedback. The same problem applies to review fix-retry: a fresh worker addresses findings without knowing *why* the original worker made each choice.

Claude Code CLI supports `--resume <session_id>` which continues a conversation with its full prior context. The resumed worker remembers what it built, what approaches it tried, and can intelligently respond to eval failures or review findings rather than starting from scratch.

This is the single highest-impact improvement to the retry loop — verified working with the CLI, minimal code change, graceful fallback to fresh dispatch if resume fails.

## What Changes

- Capture `session_id` from Claude CLI JSON output after each worker dispatch
- Store `session_id` on the `WorkerResult` model
- On eval-failure retries, use `--resume <session_id>` so the worker retains full context
- On review fix-retry, use `--resume <session_id>` so the original worker addresses its own findings
- Monitor context usage — if prior dispatch used >60% of the context window (measured as `(input_tokens + output_tokens) / contextWindow`), fall back to fresh dispatch (avoid compaction-degraded context)
- Graceful fallback: if `--resume` fails for any reason, fall back to current behavior (fresh dispatch with feedback)

## Capabilities

### New Capabilities
- `session-resume`: Capture and reuse Claude CLI session IDs for eval retries and review fix-retry, with context-aware fallback to fresh dispatch.

### Modified Capabilities
None

## Impact

- `models.py` — add `session_id: str | None` field to `WorkerResult`
- `worker.py` — capture `session_id` from JSON output, add `session_id` parameter to `dispatch_worker()`, pass `--resume` flag when resuming
- `pipeline.py` — pass `session_id` from prior `WorkerResult` into retry dispatches and review fix-retry
- No changes to eval, PR, or review agent dispatch (only the worker dispatch changes)
