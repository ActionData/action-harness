## Context

When `harness lead` starts an interactive session without a prompt, the agent must synthesize a greeting from the system prompt context. This wastes the first turn on context processing and produces inconsistent output.

## Goals / Non-Goals

**Goals:**
- Build a deterministic greeting from gathered context sections
- Pass the greeting as the initial user message so the agent responds with awareness
- Keep the greeting concise — a few lines summarizing state plus suggested directions

**Non-Goals:**
- Changing the one-shot (non-interactive) mode
- Replacing the agent persona — the greeting supplements, not replaces
- Making the greeting customizable via config

## Decisions

### 1. Structured context return from gather functions

`gather_lead_context` currently returns a flat string. Add a `LeadContext` dataclass that holds both the flat string (for system prompt) and the individual section data (repo name, active changes count, ready changes, recent run stats). The flat string is still used for the system prompt. The structured data feeds the greeting builder.

**Why:** The greeting builder needs structured data (counts, names, statuses) not prose. Parsing the flat string back would be fragile.

### 2. Greeting as initial user message

When no user prompt is provided, build a greeting prompt and pass it as the positional argument to `claude`. The agent then responds to this structured summary rather than generating one from scratch.

The greeting prompt is framed as an instruction: "Here is the current repo state. Greet me and suggest directions." This lets the agent use its persona to format the response while starting from structured data.

**Why:** Passing structured context as the user message means the agent gets both the full system prompt context (for ongoing conversation) and a focused summary (for immediate response).

### 3. Greeting format

The greeting prompt includes:
- Repo name (from directory name)
- Active changes with progress
- Recent run success rate
- Ready-to-implement changes
- "Introduce yourself based on this state and suggest 2-3 directions"

**Why:** These are the most actionable pieces of context. Assessment scores and catalog frequency are less immediately useful for a greeting.

## Risks / Trade-offs

- The greeting prompt adds ~200 chars to the first turn. Minor context cost.
- If gather functions fail to produce structured data, the greeting falls back to the existing behavior (no prompt, agent generates from persona).
