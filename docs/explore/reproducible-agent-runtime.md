# Reproducible Agent Runtime

## The Problem

The harness orchestrates Claude Code CLI as a black box. The CLI brings implicit state that isn't captured in the harness's code:

- `~/.claude/` settings and preferences
- `.claude/` per-project config (CLAUDE.md, skills, commands, agents)
- MCP server connections (deepwiki, etc.)
- Auth tokens (Anthropic API key)
- Model preferences
- Permission modes
- Tool configurations

If you deploy the harness on a different machine or different Anthropic account, none of this follows. The system isn't reproducible from the repo alone.

## The Spectrum

```
Least control                                    Most control
    ↓                                                ↓
claude CLI     →    Agent SDK    →    Custom Runtime
(current)          (Anthropic's)       (your own)

Black box          Structured API      Full control
Subprocess         Native Python       Your client
Implicit config    Some config         All in code
No session mgmt    Some control        Full control
```

## What Each Level Gives You

### Claude CLI (current)
- Battle-tested, works today
- Upstream improvements for free
- But: implicit config, no session persistence, no streaming events

### Agent SDK
- Native Python async
- Structured messages
- Hooks and subagents
- But: still needs MCP config, still uses Claude's internal tool system

### Custom Runtime
- Every tool defined in code
- MCP connections configured in code
- System prompts, model selection, context management — all code
- `git clone && pip install && run` on any machine
- Session persistence (solves same-context fix-retry)
- But: must reimplement file I/O, shell access, web search

## What Needs to Be Reproducible

For the harness to be truly portable:

1. **Tools**: file read/write, shell, git, gh — these are standard and don't need config
2. **MCP servers**: deepwiki access for openspec review — currently requires claude CLI config
3. **Agent definitions**: review agent prompts — already hardcoded in review_agents.py (good)
4. **Auth**: Anthropic API key — env var is fine
5. **Model selection**: --model flag handles this
6. **Skills/commands**: opsx:apply, opsx:archive — these are .claude/ files in the target repo

The gap is mostly MCP servers. If the harness called the Anthropic API directly, it could configure MCP connections in its own code instead of relying on claude CLI's config.

## What the Anthropic Harness Article Reinforces

The "Effective Harnesses for Long-Running Agents" article (see `docs/research/long-running-agent-harness-patterns.md`) describes patterns that all point toward a reproducible runtime:

- **`init.sh` setup scripts** — the harness should bootstrap its own environment. Maps to a `## Setup` section in HARNESS.md or equivalent config-as-code.
- **Progress files** — cross-session memory needs to be managed by the orchestrator, not left to implicit CLI state.
- **Session startup checklists** — every dispatch verifies environment health before working. The harness should own this, not depend on CLI internals.
- **Feature list as structured data** — JSON over Markdown because the format constrains agent behavior. This is easier to enforce when you control the runtime.

The meta-principle: **agents work best with the same artifacts and signals humans use.** A reproducible runtime ensures those artifacts and signals are defined in code, not scattered across implicit config.

## Timeline

```
NOW          → claude CLI + --resume (fix-retry with session continuity)
NEAR TERM    → progress files as fallback (cross-session memory)
MEDIUM TERM  → Agent SDK investigation (structured API, some config-as-code)
LONGER TERM  → custom runtime (full reproducibility, all config in code)
```

The `--resume` discovery (see `same-context-fix-retry.md`) buys significant time. Session continuity was the most urgent gap, and CLI handles it today. The reproducibility gap (MCP servers, preferences, tool config) is real but less urgent — the harness currently only runs on one machine.

The trigger to move faster on this is: needing to deploy the harness on a second machine or CI environment. At that point, implicit config becomes a blocker.

## Decision: Investigate (Deferred, Not Urgent)

The Agent SDK is the natural next step — it's the middle ground between CLI subprocess and building everything from scratch. If the SDK supports:
- Conversation continuation (for same-context fix-retry)
- MCP server configuration in code
- Tool definition in code

Then it might be all we need. If not, a custom runtime is the path, but it's a significant undertaking.

For now, the CLI with `--resume` covers the most pressing need (fix-retry continuity). Reproducibility becomes urgent when deployment context changes.

## Captured In

- **`session-resume`** (roadmap item 1) — `--resume` for eval retries and review fix-retry. Addresses the most pressing session continuity gap.
- **`retry-progress`** (roadmap item 2) — Progress file + pre-work eval as fallback when `--resume` isn't available.
- The reproducible runtime investigation itself is NOT yet a roadmap item — deferred until deployment context changes (second machine, CI environment).

## Related

- See `same-context-fix-retry.md` — session persistence is a key capability (now solved with `--resume`)
- See `docs/research/long-running-agent-harness-patterns.md` — Anthropic's harness patterns article
- See `live-progress-feed` on roadmap (item 15) — streaming requires more than CLI `-p` mode
- See `checkpoint-resume` on roadmap (item 14) — cross-stage state persistence
