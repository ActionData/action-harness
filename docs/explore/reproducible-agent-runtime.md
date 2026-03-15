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

## Decision: Investigate

The Agent SDK is the natural next step — it's the middle ground between CLI subprocess and building everything from scratch. If the SDK supports:
- Conversation continuation (for same-context fix-retry)
- MCP server configuration in code
- Tool definition in code

Then it might be all we need. If not, a custom runtime is the path, but it's a significant undertaking.

## Related

- See `same-context-fix-retry.md` — session persistence is a key capability
- See `live-progress-feed` on roadmap — streaming requires more than CLI `-p` mode
- See `checkpoint-resume` on roadmap — state persistence is related
