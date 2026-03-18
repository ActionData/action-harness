## Why

Named leads (from `named-lead-registry`) can be started and resumed, but they don't learn. A lead that's been triaging UI bugs for a week should know which components are flaky, what patterns cause regressions, and what was tried before. Today, when a session's context window compresses or the session expires, all of that knowledge is lost.

Gastown solves this with `gt prime` — a context refresh that re-injects identity, assigned work, memories, and mail after every session start and context compaction. We need the same for leads.

## What Changes

- Each lead gets a `memory.md` file in its state directory (`$HARNESS_HOME/leads/<repo>/<name>/memory.md`)
- The lead self-updates memory.md during sessions using standard file tools (Write/Edit). This is an explicit exception to the "no direct code edits" rule — memory.md is lead state, not application code.
- On session start, memory.md is injected as an additional section in `gather_lead_context`, delivered via the existing `--append-system-prompt` path alongside repo context
- After context compression, memory + identity are re-injected via a two-hook pattern (see below)
- The lead persona includes memory maintenance instructions: what to save, when to write, and size budget
- Fresh sessions (when resume fails) inject memory.md so the lead picks up where it left off conceptually

### Context re-injection after compaction

PostCompact hooks **cannot** inject context — they are observability-only. Instead, we use a two-hook pattern:

1. **PostCompact hook** — writes a flag file (`$HARNESS_HOME/leads/<repo>/<name>/.needs-prime`) indicating compaction occurred
2. **UserPromptSubmit hook** — on every user message, checks for the flag file. If present, deletes the flag and injects memory.md + lead identity + purpose via `additionalContext`. This gives one-turn-delayed re-injection after compaction.

The harness sets `HARNESS_LEAD_NAME` and `HARNESS_LEAD_DIR` environment variables when dispatching the lead session, so hook scripts can resolve the correct lead's state directory.

Hooks are registered in the project-level `.claude/settings.json` so they apply to all leads in the repo.

### Memory self-update convention

The lead persona instructs the lead to update memory.md:
- **When**: before ending a session, after making a significant decision, or when learning something that would be valuable if the session were lost
- **What to save**: key decisions, domain knowledge, patterns discovered, what's been tried, open questions
- **What NOT to save**: anything derivable from the codebase or git history (same rules as auto-memory)
- **Size budget**: keep under 200 lines (~4000 tokens). When approaching the limit, prune stale entries and distill verbose notes.
- **Format**: freeform markdown with optional section headers (e.g., `## Decisions`, `## Domain Knowledge`, `## Open Questions`). No required schema — the lead organizes as it sees fit.

## Capabilities

### New Capabilities
- `lead-memory`: Per-lead persistent knowledge store with self-update convention, session-start injection, and post-compaction re-injection via two-hook pattern

### Modified Capabilities
- `lead-interactive`: Injects memory.md via `gather_lead_context` on session start; sets `HARNESS_LEAD_NAME` and `HARNESS_LEAD_DIR` env vars for hook scripts

## Impact

- `src/action_harness/lead.py` — `gather_lead_context` extended to include memory.md content; `dispatch_lead_interactive` sets lead env vars
- `src/action_harness/lead_registry.py` — extended with memory file path resolution and initialization
- New: `.claude/hooks/lead-prime.sh` — shell script for UserPromptSubmit hook that checks the prime flag and injects memory
- New: `.claude/hooks/lead-compact-flag.sh` — shell script for PostCompact hook that writes the prime flag
- `.claude/settings.json` — hook registration for PostCompact and UserPromptSubmit
- `.harness/agents/lead.md` — gains memory maintenance instructions and self-update guidance

## Prerequisites

Requires `named-lead-registry`. Memory files live in the lead state directory it creates. Lead env vars depend on the dispatch changes in that phase.

## Inspiration

Gastown's `gt prime` command: detects role, discovers assigned work, injects memories from a KV store, and re-runs on context compaction. We adapt this to Claude Code's hook system (UserPromptSubmit for injection, PostCompact for flag-setting) and file-based memory.
