## Why

The harness executes work but doesn't plan it. Today, a human reads the repo state (roadmap, issues, codebase), decides what to work on, writes specs, and runs `harness run`. This planning step is the bottleneck — especially for repos where the human isn't deeply familiar with the codebase.

The repo lead formalizes planning as a harness command: `harness lead --repo <path> "prompt"`. It spawns a Claude Code session pre-loaded with repo context (roadmap, issues, catalog, assessment scores) and can draft OpenSpec proposals, create issues, or dispatch harness runs. Phase 1 is interactive (human provides the prompt). Phases 2-3 (event-driven, scheduled) come via `always-on`.

## What Changes

- New CLI command: `harness lead --repo <path> "prompt"` — spawns a Claude Code session with repo-lead context
- New agent definition: `.harness/agents/lead.md` with the repo-lead persona
- Context injection: reads ROADMAP.md, CLAUDE.md, HARNESS.md, open issues, assessment scores, catalog frequency, recent run report
- Optional `--dispatch` flag: after the lead produces a plan, automatically dispatch `harness run` for the recommended changes
- Handles repos with and without OpenSpec — bootstraps `openspec init` if needed, or falls back to `--prompt` mode

## Capabilities

### New Capabilities
- `repo-lead`: Interactive planning agent that reads repo context and produces actionable plans (proposals, issues, harness dispatches).

### Modified Capabilities
None

## Impact

- `cli.py` — new `lead` command
- New module `src/action_harness/lead.py` — context gathering, session dispatch, plan parsing
- `.harness/agents/lead.md` — repo-lead agent persona
- Reads existing harness data: manifests, catalog, assessment, dashboard state
- Dispatches `harness run` as a subprocess (reuses existing pipeline)
