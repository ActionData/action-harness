# lead-greeting

## Summary

Build a deterministic greeting from gathered lead context and pass it as the initial user message in interactive sessions, replacing the current behavior of relying on the LLM to synthesize a greeting from system prompt context.

## Interface

### `LeadContext` dataclass

```python
@dataclass
class LeadContext:
    full_text: str
    repo_name: str
    active_changes: list[str]
    completed_changes: list[str]
    ready_changes: list[str]
    recent_run_stats: tuple[int, int] | None  # (passed, total)
    has_roadmap: bool
    has_claude_md: bool
```

### `build_greeting(ctx: LeadContext) -> str`

Builds a concise prompt for the lead agent's first turn. Example output:

```
You are leading action-harness. Active changes: always-on-webhook. Ready to implement: always-on-webhook. Recent runs: 4/5 passed. Greet me with a brief status summary and suggest 2-3 directions we could go.
```

### Modified: `gather_lead_context` → returns `LeadContext`

Previously returned `str`. Now returns `LeadContext` with `full_text` containing the same assembled string. Callers using the flat string use `.full_text`.

### Modified: `dispatch_lead_interactive` context parameter

Changes from `context: str` to `context: LeadContext`. Uses `context.full_text` for system prompt. When no user prompt is given, calls `build_greeting(context)` as the initial message.

## Behavior

- When user provides a prompt: that prompt is used as-is (no change)
- When user provides no prompt: `build_greeting` output is used as the initial message
- Greeting is deterministic — same context produces same greeting
- If LeadContext has no useful data (empty repo), greeting is minimal: just repo name + "Greet me"
