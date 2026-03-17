## Why

The `harness lead` command dispatches a one-shot Claude Code session (`claude -p`) that produces a structured JSON plan. This works for autonomous dispatch but is unusable for the primary use case: a human sitting down to plan work on a repo. The human wants a conversation — explore ideas, ask follow-ups, refine proposals — not a fire-and-forget JSON blob. Today they must manually open Claude Code, load context themselves, and lose the pre-gathered repo context that `harness lead` assembles.

## What Changes

- Add `--interactive` / `-i` flag to `harness lead` that spawns a conversational Claude Code session instead of the one-shot dispatch
- Interactive mode writes a temporary system prompt file containing the lead persona + gathered context, then runs `claude` (without `-p`) so the human can interact naturally
- The initial user prompt is passed via `--initial-prompt` so the conversation starts with the user's request while remaining interactive
- Plan parsing and `--dispatch` are skipped in interactive mode — the human drives the session
- Make interactive the default mode (no flag needed), with `--non-interactive` for the existing one-shot behavior

## Capabilities

### New Capabilities
- `lead-interactive`: Interactive lead session with pre-gathered repo context and conversational Claude Code dispatch

### Modified Capabilities
- `repo-lead`: Default mode changes from one-shot to interactive. Existing non-interactive behavior preserved via `--non-interactive` flag.

## Impact

- `cli.py` — modify `lead` command: add `--interactive` flag (default True), rename dispatch logic path
- `lead.py` — add `dispatch_lead_interactive()` function for interactive session dispatch
- Tests for the new interactive dispatch path
- No changes to context gathering, agent definitions, or plan parsing
