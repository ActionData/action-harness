## Context

The harness dispatches Claude Code workers via `subprocess.run(["claude", "-p", ...])`. The JSON output includes a `session_id` field that can be used with `--resume` to continue the same conversation. Currently, each dispatch starts fresh — the retry loop passes eval feedback as a string, but the worker has no memory of its prior work.

The `same-context-fix-retry.md` explore doc verified that `--resume` works in headless mode. The `long-running-agent-harness-patterns.md` research doc (from Anthropic's engineering blog) identifies session continuity as the core problem for long-running agent work.

## Goals / Non-Goals

**Goals:**
- Resume worker sessions on eval-failure retries
- Resume worker sessions on review fix-retry
- Context-aware decision: resume when context is fresh, fresh dispatch when context is exhausted
- Graceful fallback: if resume fails, fall back to current behavior

**Non-Goals:**
- Progress files (that's the `retry-progress` change — complements this as a fallback)
- Agent SDK migration (longer-term, see `docs/explore/reproducible-agent-runtime.md`)
- Resuming across pipeline stages (that's `checkpoint-resume`)
- Session persistence beyond a single pipeline run

## Decisions

### 1. Capture `session_id` from JSON output

The Claude CLI JSON output already includes `session_id`. The harness captures it and stores it on `WorkerResult.session_id`. This is the only model change needed.

```python
# Already in worker.py JSON parsing:
output_data = json.loads(result.stdout)
cost_usd = output_data.get("cost_usd")
# Add:
session_id = output_data.get("session_id")
```

### 2. `dispatch_worker()` accepts optional `session_id` for resume

When `session_id` is provided, the CLI command includes `--resume <session_id>`. The user prompt becomes just the feedback (not the full opsx:apply instruction, since the resumed session already has that context). If `session_id` is provided but `feedback` is None, this is a programming error — raise `ValueError("resume requires feedback")`.

```
Fresh dispatch:
  claude -p "Implement change X using opsx:apply" --system-prompt "..." --output-format json

Resumed dispatch:
  claude -p "Eval failed: <feedback>" --resume <session_id> --output-format json
```

Note: `--system-prompt` is omitted on resume since the session already has it. The `-p` flag sends just the new feedback as the next user message.

**Alternative considered:** Sending both `--system-prompt` and `--resume`. Rejected — the resumed session already has the system prompt, and re-sending it may cause confusion or duplicate instructions.

### 3. Context-aware resume vs fresh dispatch

The JSON output includes token counts and the model's context window size. After each dispatch, compute:

```python
# Actual CLI JSON structure (verified):
# usage.input_tokens, usage.output_tokens — top-level usage
# modelUsage.<model_id>.contextWindow — e.g. modelUsage["claude-opus-4-6[1m]"].contextWindow
#
# Use the first (and typically only) model in modelUsage:
model_info = next(iter(output_data.get("modelUsage", {}).values()), {})
context_window = model_info.get("contextWindow", 1_000_000)
input_tokens = output_data.get("usage", {}).get("input_tokens", 0)
output_tokens = output_data.get("usage", {}).get("output_tokens", 0)
context_usage_pct = (input_tokens + output_tokens) / context_window
```

If `context_usage_pct > 0.6` (60% of window used), skip `--resume` and use a fresh dispatch with feedback on the next retry. This avoids compaction-degraded context where the agent's earlier reasoning has been summarized away.

The 60% threshold is a starting heuristic. It can be tuned based on observed retry quality.

### 4. Fallback to fresh dispatch on resume failure

If `--resume` fails (expired session, CLI error, etc.), the harness falls back to a fresh dispatch with the eval feedback as a string — exactly the current behavior. This makes the change purely additive with no regression risk.

### 5. Review fix-retry uses the original worker's session

`_run_review_fix_retry` in `pipeline.py` currently dispatches a fresh worker with review feedback. With this change, it uses `--resume` with the session_id from the last successful worker dispatch (the one that produced the code being reviewed). This means the original worker addresses its own review findings with full context of why it made each choice.

## Risks / Trade-offs

- [Session expiration] Claude CLI session IDs may expire after some time → Mitigation: graceful fallback to fresh dispatch. The harness logs a warning and continues.
- [Context exhaustion] Long sessions may hit compaction, degrading quality → Mitigation: the 60% threshold triggers fresh dispatch before compaction degrades context significantly.
- [Compaction heuristic] 60% may not be the right threshold → Mitigation: make it configurable via an environment variable or flag if needed. Start with 60% and adjust based on observed behavior.
- [Resume changes behavior] A resumed session may behave differently than a fresh one → Mitigation: the eval gate catches any regressions regardless of dispatch mode.
